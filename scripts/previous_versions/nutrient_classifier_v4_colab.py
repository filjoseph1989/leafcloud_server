# ============================================================
# LeafCloud — Nutrient Classifier V4 (Google Colab Version)
# ============================================================
# Before running:
#   1. Run scripts/export_for_colab.py on your local machine
#   2. Upload exports/colab_training_data.csv to Google Drive
#   3. Upload exports/colab_crops.zip to Google Drive
#   4. Paste this file into a Colab notebook cell (or upload as .py)
# ============================================================

# ----- Cell 1: Install dependencies -----
# !pip install -q tqdm scikit-learn

# ----- Cell 2: Mount Google Drive -----
# from google.colab import drive
# drive.mount('/content/drive')

# ----- Cell 3: Unzip crops (run once) -----
# import zipfile
# ZIP_PATH    = '/content/drive/MyDrive/leafcloud/colab_crops.zip'
# EXTRACT_DIR = '/content/crops'
# with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
#     zf.extractall(EXTRACT_DIR)
# print('✅ Crops extracted')

# ============================================================
# Configuration — update these paths to match your Drive layout
# ============================================================
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
from sklearn.model_selection import StratifiedShuffleSplit
from tqdm import tqdm

# ---- UPDATE THESE ----
CSV_PATH        = '/content/drive/MyDrive/leafcloud/colab_training_data.csv'
CROPS_BASE_DIR  = '/content/crops'   # where you extracted colab_crops.zip
MODEL_SAVE_DIR  = '/content/drive/MyDrive/leafcloud/models'
# ----------------------

IMG_SIZE   = (224, 224)
BATCH_SIZE = 32
TIMESTAMP  = datetime.now().strftime('%Y%m%d_%H%M')
MODEL_SAVE_PATH = os.path.join(MODEL_SAVE_DIR, f'leafcloud_multimodal_v4_{TIMESTAMP}.keras')

os.makedirs(MODEL_SAVE_DIR, exist_ok=True)

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 3.0),
    'water_temp': (24.0, 29.0),
}

LABEL_LIST   = ['Water', 'NPK', 'Micro', 'Mix']
LABEL_TO_IDX = {l: i for i, l in enumerate(LABEL_LIST)}

CONCENTRATION_MAP = {
    'Water': [0.0, 0.0],
    'NPK':   [1.0, 0.0],
    'Micro': [0.0, 1.0],
    'Mix':   [1.0, 1.0],
}


def remap_path(original_path: str) -> str:
    """Remaps the local image path stored in the CSV to the Colab extraction path."""
    return os.path.join(CROPS_BASE_DIR, original_path)


def get_dataset():
    print(f'📄 Loading CSV: {CSV_PATH}')
    df = pd.read_csv(CSV_PATH)
    print(f'  {len(df)} records loaded')
    print(df['bucket_label'].value_counts())

    # Remap paths to Colab filesystem
    df['image_path'] = df['image_path'].apply(remap_path)

    print('\n🔍 Verifying image files...')
    valid_mask = []
    for path in tqdm(df['image_path'], desc='Checking files'):
        try:
            with open(path, 'rb') as f:
                f.read(1)
            valid_mask.append(True)
        except:
            valid_mask.append(False)

    missing = sum(1 for v in valid_mask if not v)
    if missing:
        print(f'⚠️  {missing} inaccessible files removed.')
    df = df[valid_mask].reset_index(drop=True)
    print(f'✅ {len(df)} valid images found.')

    # Normalize sensors
    for col, (lo, hi) in SENSOR_NORM.items():
        df[col] = (df[col].clip(lo, hi) - lo) / (hi - lo)

    df['label_idx'] = df['bucket_label'].map(LABEL_TO_IDX)
    targets = df['bucket_label'].map(CONCENTRATION_MAP)
    df['macro_val'] = [t[0] for t in targets]
    df['micro_val'] = [t[1] for t in targets]

    # Inverse-frequency sample weights
    counts   = df['bucket_label'].value_counts()
    n_total  = len(df)
    n_classes = len(counts)
    df['sample_weight'] = df['bucket_label'].map(
        {label: n_total / (n_classes * count) for label, count in counts.items()}
    )

    # Stratified split
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(splitter.split(df, df['label_idx']))
    train_df = df.iloc[train_idx].reset_index(drop=True)
    val_df   = df.iloc[val_idx].reset_index(drop=True)

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
        images    = np.array([self._load_image(p) for p in batch['image_path']])
        sensors   = batch[['ph', 'ec', 'water_temp']].values.astype(np.float32)
        labels_clf = tf.keras.utils.to_categorical(batch['label_idx'].values, num_classes=4)
        labels_reg = batch[['macro_val', 'micro_val']].values.astype(np.float32)
        weights   = batch['sample_weight'].values.astype(np.float32)
        return (images, sensors), {'clf_output': labels_clf, 'reg_output': labels_reg}, weights


def build_model_v4():
    base_model = MobileNetV2(weights='imagenet', include_top=False,
                             input_shape=(IMG_SIZE[0], IMG_SIZE[1], 3))
    base_model.trainable = False

    img_input = base_model.input
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    x = Dense(128, activation='relu')(x)
    x = Dropout(0.4)(x)

    sensor_input = Input(shape=(3,), name='sensor_input')
    s = Dense(128, activation='relu')(sensor_input)
    s = BatchNormalization()(s)
    s = Dense(64, activation='relu')(s)
    s = Dropout(0.2)(s)

    merged = Concatenate()([x, s])
    merged = Dense(128, activation='relu')(merged)
    merged = Dropout(0.3)(merged)

    clf_output = Dense(4, activation='softmax', name='clf_output')(merged)

    reg_branch = Dense(64, activation='relu')(merged)
    reg_branch = Dropout(0.2)(reg_branch)
    reg_branch = Dense(32, activation='relu')(reg_branch)
    reg_output = Dense(2, activation='sigmoid', name='reg_output')(reg_branch)

    model = Model(inputs=[img_input, sensor_input], outputs=[clf_output, reg_output])
    return model, base_model


def compile_and_fit(model, train_gen, val_gen, optimizer, loss_weights, epochs, callbacks):
    model.compile(
        optimizer=optimizer,
        loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
        loss_weights=loss_weights,
        metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
    )
    return model.fit(train_gen, validation_data=val_gen, epochs=epochs, callbacks=callbacks)


if __name__ == '__main__':
    print(f'TensorFlow version: {tf.__version__}')
    print(f'GPU available: {tf.config.list_physical_devices("GPU")}')

    train_df, val_df = get_dataset()

    if train_df.empty:
        print('❌ No data found. Check CSV_PATH and CROPS_BASE_DIR.')
    else:
        train_gen = MultiModalGenerator(train_df, BATCH_SIZE, IMG_SIZE, augment=True)
        val_gen   = MultiModalGenerator(val_df,   BATCH_SIZE, IMG_SIZE, augment=False)

        print('\n🧠 Building Multi-Task Multi-Modal Model (V4)...')
        model, base_model = build_model_v4()
        model.summary()

        early_stop_clf = EarlyStopping(
            monitor='val_clf_output_accuracy', patience=10,
            restore_best_weights=True, mode='max', verbose=1
        )
        early_stop_reg = EarlyStopping(
            monitor='val_reg_output_mae', patience=8,
            restore_best_weights=True, mode='min', verbose=1
        )
        reduce_lr = ReduceLROnPlateau(
            monitor='val_loss', factor=0.5, patience=5, min_lr=1e-6, verbose=1
        )

        print('\n🚀 Phase 1 — Classification Warm-up...')
        compile_and_fit(model, train_gen, val_gen,
                        optimizer=Adam(0.0005),
                        loss_weights={'clf_output': 1.0, 'reg_output': 0.0},
                        epochs=50, callbacks=[early_stop_clf])

        print('\n🚀 Phase 2 — Joint Training (reg_weight=0.3)...')
        compile_and_fit(model, train_gen, val_gen,
                        optimizer=Adam(0.0005),
                        loss_weights={'clf_output': 1.0, 'reg_output': 0.3},
                        epochs=40, callbacks=[early_stop_clf, reduce_lr])

        print('\n🔓 Phase 3 — Fine-tune Top MobileNet Layers...')
        base_model.trainable = True
        for layer in base_model.layers[:-30]:
            layer.trainable = False
        compile_and_fit(model, train_gen, val_gen,
                        optimizer=Adam(1e-5),
                        loss_weights={'clf_output': 1.0, 'reg_output': 0.3},
                        epochs=30, callbacks=[early_stop_clf, reduce_lr])

        print('\n🎯 Phase 4 — Regression Focus (reg_weight=0.8)...')
        compile_and_fit(model, train_gen, val_gen,
                        optimizer=Adam(5e-6),
                        loss_weights={'clf_output': 1.0, 'reg_output': 0.8},
                        epochs=20, callbacks=[early_stop_reg, reduce_lr])

        model.save(MODEL_SAVE_PATH)
        print(f'\n✅ Model saved to {MODEL_SAVE_PATH}')
        print('Download it from Google Drive and set AI_MODEL_PATH in your .env')
