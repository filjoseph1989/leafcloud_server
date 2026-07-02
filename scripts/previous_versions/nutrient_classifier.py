import os
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
from tensorflow.keras.callbacks import EarlyStopping
from sqlalchemy import create_engine
from tqdm import tqdm
from app.core.config import settings

# ==========================================
# CONFIGURATION - SENSOR-BOOSTED VERSION
# ==========================================
DB_URL = settings.DATABASE_URL
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M')
MODEL_SAVE_PATH = f'leafcloud_sensor_boost_{TIMESTAMP}.keras'

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 3.0),
    'water_temp': (24.0, 29.0),
}

# Mapping for 4-class classification
LABEL_LIST = ['Water', 'NPK', 'Micro', 'Mix']
LABEL_TO_IDX = {l: i for i, l in enumerate(LABEL_LIST)}

def fetch_raw_data(engine) -> pd.DataFrame:
    """Fetches the linked crops, readings, and experiments from the database."""
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
    """Removes records where the image file is not accessible on disk."""
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
    """Scales sensor data to 0-1 range based on predefined thresholds."""
    for col, (lo, hi) in SENSOR_NORM.items():
        df[col] = (df[col].clip(lo, hi) - lo) / (hi - lo)
    return df

def calculate_sample_weights(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates weights to handle class imbalance during training."""
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
        return df

    print(f'✅ {len(df)} valid images found.')

    df = apply_normalization(df)
    
    # Encode labels for classification
    df['label_idx'] = df['bucket_label'].map(LABEL_TO_IDX)
    
    df = calculate_sample_weights(df)

    return df

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
        
        # Apply augmentation on raw pixels if enabled
        if self.augment:
            img = tf.image.random_flip_left_right(img)
            img = tf.image.random_brightness(img, 0.1)
            img = tf.image.random_contrast(img, 0.9, 1.1)
        
        # MobileNetV2 Preprocessing (expects 0-255, outputs -1 to 1)
        img = preprocess_input(img)
        return img.numpy()

    def __getitem__(self, idx):
        batch_idx = self.indices[idx * self.batch_size:(idx + 1) * self.batch_size]
        batch     = self.df.iloc[batch_idx]

        images  = np.array([self._load_image(p) for p in batch['image_path']])
        sensors = batch[['ph', 'ec', 'water_temp']].values.astype(np.float32)
        
        # Convert index to one-hot labels
        labels  = tf.keras.utils.to_categorical(batch['label_idx'].values, num_classes=4)
        weights = batch['sample_weight'].values.astype(np.float32)

        return (images, sensors), labels, weights

def build_model_sensor_boosted():
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
    x = Dense(64, activation='relu')(x)
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
    
    # Final Layer: 4 Units for 4-class Classification
    output = Dense(4, activation='softmax')(merged)

    model = Model(inputs=[img_input, sensor_input], outputs=output)
    model.compile(
        optimizer=Adam(learning_rate=0.0005),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )

    return model, base_model

if __name__ == '__main__':
    df = get_dataset()

    if df.empty:
        print('❌ No data found.')
    else:
        split = int(len(df) * 0.8)
        df_shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)
        train_gen = MultiModalGenerator(df_shuffled.iloc[:split], BATCH_SIZE, IMG_SIZE, augment=True)
        val_gen   = MultiModalGenerator(df_shuffled.iloc[split:], BATCH_SIZE, IMG_SIZE, augment=False)

        print('🧠 Building Sensor-Boosted Classification Model...')
        model, base_model = build_model_sensor_boosted()
        model.summary()

        early_stop = EarlyStopping(
            monitor='val_accuracy',
            patience=10,
            restore_best_weights=True,
            mode='max',
            verbose=1
        )

        print('\n🚀 Phase 1 Training...')
        model.fit(train_gen, validation_data=val_gen, epochs=50, callbacks=[early_stop])

        print('\n🔓 Phase 2 Fine-tuning...')
        base_model.trainable = True
        # Fine-tune more layers for classification complexity
        for layer in base_model.layers[:-30]:
            layer.trainable = False
        
        model.compile(optimizer=Adam(learning_rate=1e-5), loss='categorical_crossentropy', metrics=['accuracy'])
        model.fit(train_gen, validation_data=val_gen, epochs=30, callbacks=[early_stop])

        model.save(MODEL_SAVE_PATH)
        print(f'\n✅ Model saved to {MODEL_SAVE_PATH}')
