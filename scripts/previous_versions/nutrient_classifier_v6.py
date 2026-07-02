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
# CONFIGURATION - MULTI-TASK V6
# ==========================================
DB_URL = settings.DATABASE_URL
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M')
MODEL_SAVE_PATH = f'leafcloud_multimodal_v6_{TIMESTAMP}.keras'

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 1.6),   # normalized range matching actual data limits
    'water_temp': (24.0, 29.0),
}

LABEL_LIST = ['Water', 'NPK', 'Micro', 'Mix']
LABEL_TO_IDX = {l: i for i, l in enumerate(LABEL_LIST)}


def fetch_raw_data(engine) -> pd.DataFrame:
    query = """
    SELECT
        ic.crop_path  AS image_path,
        cdr.ph,
        cdr.ec,
        cdr.water_temp,
        cdr.timestamp,
        cdr.experiment_id,
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


def calculate_continuous_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates continuous targets for Macro and Micro scaling based on real-time EC depletion.
    Formula: Target = (Current EC - Water Base EC) / (Initial EC - Water Base EC)
    """
    print('\n📈 Calculating continuous depletion targets (V6)...')
    
    # 1. Compute baseline EC of pure water in the dataset
    water_df = df[df['bucket_label'] == 'Water']
    water_base_ec = float(water_df['ec'].mean()) if not water_df.empty else 0.05
    print(f'  Computed water baseline EC: {water_base_ec:.4f} mS/cm')

    # 2. Compute initial EC at start of each experiment (earliest timestamp reading)
    initial_ec_map = {}
    for exp_id, group in df.groupby('experiment_id'):
        if len(group) > 0:
            # Find row with earliest timestamp
            earliest_row = group.loc[group['timestamp'].idxmin()]
            initial_ec_map[exp_id] = float(earliest_row['ec'])
    
    # Print calculated initial EC values for debugging
    print('  Initial EC values per experiment:')
    for exp_id, init_ec in initial_ec_map.items():
        print(f'    Experiment {exp_id}: {init_ec:.4f} mS/cm')

    macro_vals = []
    micro_vals = []

    # 3. Calculate ratio based on bucket labels
    for idx, row in df.iterrows():
        label = row['bucket_label']
        exp_id = row['experiment_id']
        current_ec = row['ec']

        if label == 'Water':
            # Water has 0 nutrients, no depletion curve
            macro_vals.append(0.0)
            micro_vals.append(0.0)
        else:
            initial_ec = initial_ec_map.get(exp_id, current_ec)
            denominator = initial_ec - water_base_ec
            
            # Avoid division by zero or extremely small denominators due to noise
            if denominator < 0.1:
                denominator = 0.1
                
            # Depletion ratio represents how much of the initial dose remains
            ratio = (current_ec - water_base_ec) / denominator
            # Clip between [0, 1] to guard against sensor noise or initial anomalies
            ratio = float(np.clip(ratio, 0.0, 1.0))

            if label == 'NPK':
                macro_vals.append(ratio)
                micro_vals.append(0.0)
            elif label == 'Micro':
                macro_vals.append(0.0)
                micro_vals.append(ratio)
            elif label == 'Mix':
                # In Mix buckets, both elements deplete together
                macro_vals.append(ratio)
                micro_vals.append(ratio)

    df['macro_val'] = macro_vals
    df['micro_val'] = micro_vals
    
    print('  Target calculation complete.')
    print(f"  Macro scale range: min={df['macro_val'].min():.2f}, max={df['macro_val'].max():.2f}, mean={df['macro_val'].mean():.2f}")
    print(f"  Micro scale range: min={df['micro_val'].min():.2f}, max={df['micro_val'].max():.2f}, mean={df['micro_val'].mean():.2f}")
    return df


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

    # Calculate continuous regression targets before sensor normalization
    df = calculate_continuous_targets(df)
    
    df = apply_normalization(df)
    df['label_idx'] = df['bucket_label'].map(LABEL_TO_IDX)

    df = calculate_sample_weights(df)

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


def build_model_v6():
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
    x = Dense(256, activation='relu')(x)
    x = Dropout(0.4)(x)

    # Sensor Branch
    sensor_input = Input(shape=(3,), name='sensor_input')
    s = Dense(64, activation='relu')(sensor_input)
    s = BatchNormalization()(s)
    s = Dense(64, activation='relu')(s)
    s = BatchNormalization()(s)
    s = Dense(32, activation='relu')(s)
    s = Dropout(0.2)(s)

    # Fusion
    merged = Concatenate()([x, s])
    merged = Dense(256, activation='relu')(merged)
    merged = Dropout(0.3)(merged)

    # Classification Branch
    clf_branch = Dense(64, activation='relu')(merged)
    clf_branch = Dropout(0.2)(clf_branch)
    clf_output = Dense(4, activation='softmax', name='clf_output')(clf_branch)

    # Dedicated Regression Branch
    reg_branch = Dense(64, activation='relu')(merged)
    reg_branch = Dropout(0.2)(reg_branch)
    reg_branch = Dense(32, activation='relu')(reg_branch)
    # Sigmoid limits output predictions cleanly between [0.0, 1.0]
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

        print('🧠 Building Multi-Task Multi-Modal Model (V6)...')
        model, base_model = build_model_v6()
        model.summary()

        early_stop_clf = EarlyStopping(
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
        # Establishes classification accuracy first.
        # --------------------------------------------------
        print('\n🚀 Phase 1 Training (Classification Warm-up — reg_weight=0.0)...')
        model.compile(
            optimizer=Adam(learning_rate=0.0005),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.0},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        model.fit(train_gen, validation_data=val_gen, epochs=50, callbacks=[early_stop_clf])

        # --------------------------------------------------
        # Phase 2: Joint training on continuous targets
        # --------------------------------------------------
        print('\n🚀 Phase 2 Training (Joint — reg_weight=0.05)...')
        model.compile(
            optimizer=Adam(learning_rate=0.0005),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.05},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        model.fit(train_gen, validation_data=val_gen, epochs=40,
                  callbacks=[early_stop_clf, reduce_lr])

        # --------------------------------------------------
        # Phase 3: Fine-tune top MobileNet layers
        # --------------------------------------------------
        print('\n🔓 Phase 3 Fine-tuning (Top MobileNet Layers — reg_weight=0.05)...')
        base_model.trainable = True
        for layer in base_model.layers[:-30]:
            layer.trainable = False

        model.compile(
            optimizer=Adam(learning_rate=1e-5),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.05},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        model.fit(train_gen, validation_data=val_gen, epochs=30,
                  callbacks=[early_stop_clf, reduce_lr])

        model.save(MODEL_SAVE_PATH)
        print(f'\n✅ Model saved to {MODEL_SAVE_PATH}')