import os
import sys
from datetime import datetime
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2, preprocess_input
from tensorflow.keras.layers import (
    Dense, GlobalAveragePooling2D, Dropout,
    Input, Concatenate, BatchNormalization
)
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from sqlalchemy import create_engine
from sklearn.model_selection import StratifiedShuffleSplit
from tqdm import tqdm

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.config import settings

# ==========================================
# CONFIGURATION - MULTI-TASK V4
# ==========================================
DB_URL = settings.DATABASE_URL
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M')
MODEL_SAVE_PATH = f'leafcloud_multimodal_v4_{TIMESTAMP}.keras'

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 3.0),
    'water_temp': (24.0, 29.0),
}

LABEL_LIST = ['Water', 'NPK', 'Micro', 'Mix']
LABEL_TO_IDX = {l: i for i, l in enumerate(LABEL_LIST)}

# Regression targets normalized to [0, 1] — V3 used 2.0 which caused unbounded outputs
CONCENTRATION_MAP = {
    'Water': [0.0, 0.0],
    'NPK':   [1.0, 0.0],
    'Micro': [0.0, 1.0],
    'Mix':   [1.0, 1.0],
}


def fetch_raw_data(engine) -> pd.DataFrame:
    query = """
    SELECT
        ic.crop_path  AS image_path,
        cdr.ph,
        cdr.ec,
        cdr.water_temp,
        e.bucket_label
    FROM image_crops ic
    JOIN cleaned_daily_readings cdr ON ic.daily_reading_id = cdr.id
    JOIN experiments e ON cdr.experiment_id = e.id
    WHERE e.bucket_label IN ('NPK', 'Micro', 'Mix', 'Water')
    """
    df = pd.read_sql(query, engine)
    print(f'  Fetched {len(df)} crop records')
    return df


def filter_missing_images(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    print('🔍 Verifying image files on disk...')
    def is_accessible(path):
        try:
            with open(path, 'rb') as f:
                f.read(1)
            return True
        except:
            return False
    tqdm.pandas(desc='Checking files')
    df['exists'] = df['image_path'].progress_apply(is_accessible)
    missing = (~df['exists']).sum()
    if missing:
        print(f'⚠️  {missing} inaccessible files removed.')
    return df[df['exists']].drop(columns=['exists']).reset_index(drop=True)


def apply_normalization(df: pd.DataFrame) -> pd.DataFrame:
    for col, (lo, hi) in SENSOR_NORM.items():
        df[col] = (df[col].clip(lo, hi) - lo) / (hi - lo)
    return df


def calculate_sample_weights(df: pd.DataFrame) -> pd.DataFrame:
    counts = df['bucket_label'].value_counts()
    n_total = len(df)
    n_classes = len(counts)
    weight_map = {label: n_total / (n_classes * count) for label, count in counts.items()}
    df['sample_weight'] = df['bucket_label'].map(weight_map)
    return df


def get_dataset():
    print('🔌 Connecting to Database...')
    engine = create_engine(DB_URL)

    df = fetch_raw_data(engine)
    df = filter_missing_images(df)

    if df.empty:
        return df, df

    print(f'✅ {len(df)} valid images found.')
    print('\nClass distribution:')
    print(df['bucket_label'].value_counts())

    df = apply_normalization(df)
    df['label_idx'] = df['bucket_label'].map(LABEL_TO_IDX)

    targets = df['bucket_label'].map(CONCENTRATION_MAP)
    df['macro_val'] = [t[0] for t in targets]
    df['micro_val'] = [t[1] for t in targets]

    df = calculate_sample_weights(df)

    # Stratified split — ensures each class is proportionally represented in val
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(splitter.split(df, df['label_idx']))
    train_df = df.iloc[train_idx].reset_index(drop=True)
    val_df = df.iloc[val_idx].reset_index(drop=True)

    print(f'\nTrain: {len(train_df)} | Val: {len(val_df)}')
    print('Val class distribution:')
    print(val_df['bucket_label'].value_counts())

    return train_df, val_df


class MultiModalGenerator(tf.keras.utils.Sequence):
    def __init__(self, df, batch_size, img_size, augment=False):
        super().__init__()
        self.df         = df.reset_index(drop=True)
        self.batch_size = batch_size
        self.img_size   = img_size
        self.augment    = augment
        self.indices    = np.arange(len(df))

    def __len__(self):
        return int(np.ceil(len(self.df) / self.batch_size))

    def on_epoch_end(self):
        np.random.shuffle(self.indices)

    def _load_image(self, path):
        img_raw = tf.io.read_file(path)
        img = tf.image.decode_jpeg(img_raw, channels=3)
        img = tf.image.resize(img, self.img_size)

        if self.augment:
            img = tf.image.random_flip_left_right(img)
            img = tf.image.random_flip_up_down(img)
            img = tf.image.random_brightness(img, 0.15)
            img = tf.image.random_contrast(img, 0.85, 1.15)
            img = tf.image.random_saturation(img, 0.8, 1.2)
            img = tf.image.random_hue(img, 0.05)

        img = preprocess_input(img)
        return img.numpy()

    def __getitem__(self, idx):
        batch_idx = self.indices[idx * self.batch_size:(idx + 1) * self.batch_size]
        batch     = self.df.iloc[batch_idx]

        images  = np.array([self._load_image(p) for p in batch['image_path']])
        sensors = batch[['ph', 'ec', 'water_temp']].values.astype(np.float32)

        labels_clf = tf.keras.utils.to_categorical(batch['label_idx'].values, num_classes=4)
        labels_reg = batch[['macro_val', 'micro_val']].values.astype(np.float32)
        weights = batch['sample_weight'].values.astype(np.float32)

        return (images, sensors), {'clf_output': labels_clf, 'reg_output': labels_reg}, weights


def build_model_v4():
    base_model = MobileNetV2(
        weights='imagenet',
        include_top=False,
        input_shape=(IMG_SIZE[0], IMG_SIZE[1], 3)
    )
    base_model.trainable = False

    # Image Branch
    img_input = base_model.input
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    x = Dense(128, activation='relu')(x)
    x = Dropout(0.4)(x)

    # Sensor Branch
    sensor_input = Input(shape=(3,), name='sensor_input')
    s = Dense(128, activation='relu')(sensor_input)
    s = BatchNormalization()(s)
    s = Dense(64, activation='relu')(s)
    s = Dropout(0.2)(s)

    # Fusion
    merged = Concatenate()([x, s])
    merged = Dense(128, activation='relu')(merged)
    merged = Dropout(0.3)(merged)

    # Classification head
    clf_output = Dense(4, activation='softmax', name='clf_output')(merged)

    # Dedicated regression head — separate branch reduces task interference
    reg_branch = Dense(64, activation='relu')(merged)
    reg_branch = Dropout(0.2)(reg_branch)
    reg_branch = Dense(32, activation='relu')(reg_branch)
    # Sigmoid bounds output to [0, 1] — matches normalized CONCENTRATION_MAP targets
    reg_output = Dense(2, activation='sigmoid', name='reg_output')(reg_branch)

    model = Model(inputs=[img_input, sensor_input], outputs=[clf_output, reg_output])

    return model, base_model


if __name__ == '__main__':
    train_df, val_df = get_dataset()

    if train_df.empty:
        print('❌ No data found.')
    else:
        train_gen = MultiModalGenerator(train_df, BATCH_SIZE, IMG_SIZE, augment=True)
        val_gen   = MultiModalGenerator(val_df,   BATCH_SIZE, IMG_SIZE, augment=False)

        print('🧠 Building Multi-Task Multi-Modal Model (V4)...')
        model, base_model = build_model_v4()
        model.summary()

        early_stop = EarlyStopping(
            monitor='val_clf_output_accuracy',
            patience=10,
            restore_best_weights=True,
            mode='max',
            verbose=1
        )

        reduce_lr = ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=5,
            min_lr=1e-6,
            verbose=1
        )

        # --------------------------------------------------
        # Phase 1: Classification warm-up (regression off)
        # --------------------------------------------------
        print('\n🚀 Phase 1 Training (Classification Warm-up)...')
        model.compile(
            optimizer=Adam(learning_rate=0.0005),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.0},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        model.fit(train_gen, validation_data=val_gen, epochs=50, callbacks=[early_stop])

        # --------------------------------------------------
        # Phase 2: Joint training — higher regression weight vs V3's 0.05
        # --------------------------------------------------
        print('\n🚀 Phase 2 Training (Joint — reg_weight=0.3)...')
        model.compile(
            optimizer=Adam(learning_rate=0.0005),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.3},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        model.fit(train_gen, validation_data=val_gen, epochs=40,
                  callbacks=[early_stop, reduce_lr])

        # --------------------------------------------------
        # Phase 3: Fine-tune top MobileNet layers
        # --------------------------------------------------
        print('\n🔓 Phase 3 Fine-tuning (Top MobileNet Layers)...')
        base_model.trainable = True
        for layer in base_model.layers[:-30]:
            layer.trainable = False

        model.compile(
            optimizer=Adam(learning_rate=1e-5),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.3},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        model.fit(train_gen, validation_data=val_gen, epochs=30,
                  callbacks=[early_stop, reduce_lr])

        # --------------------------------------------------
        # Phase 4: Regression-focused pass (boost regression R²)
        # --------------------------------------------------
        print('\n🎯 Phase 4 Training (Regression Focus — reg_weight=0.8)...')
        model.compile(
            optimizer=Adam(learning_rate=5e-6),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.8},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        early_stop_reg = EarlyStopping(
            monitor='val_reg_output_mae',
            patience=8,
            restore_best_weights=True,
            mode='min',
            verbose=1
        )
        model.fit(train_gen, validation_data=val_gen, epochs=20,
                  callbacks=[early_stop_reg, reduce_lr])

        model.save(MODEL_SAVE_PATH)
        print(f'\n✅ Model saved to {MODEL_SAVE_PATH}')
