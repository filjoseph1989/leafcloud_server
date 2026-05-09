import os
from datetime import datetime
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.layers import (
    Dense, GlobalAveragePooling2D, Dropout,
    Input, Concatenate, BatchNormalization
)
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam
from sqlalchemy import create_engine
from tqdm import tqdm

# ==========================================
# CONFIGURATION
# ==========================================
DB_URL = os.getenv("DATABASE_URL", "postgresql://fil:@localhost/leafcloud2")
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS_PHASE1 = 15   # frozen base — train custom head
EPOCHS_PHASE2 = 10   # unfreeze top layers — fine-tune
FINETUNE_LAYERS = 30 # number of MobileNetV2 top layers to unfreeze
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")
MODEL_SAVE_PATH = f"leafcloud_multimodal_model_{TIMESTAMP}.keras"

# Sensor normalization ranges (min, max) based on cleaned_daily_readings
SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 10.0),
    'water_temp': (15.0, 35.0),
}

# Bucket label → [npk_ml_L, micro_ml_L]
CONCENTRATION_MAP = {
    'Water': [0.0, 0.0],
    'NPK':   [2.0, 0.0],
    'Micro': [0.0, 2.0],
    'Mix':   [2.0, 2.0],
}

# ==========================================
# 1. DATA LOADING & MAPPING
# ==========================================
def get_dataset():
    print("🔌 Connecting to Database leafcloud2...")
    engine = create_engine(DB_URL)

    # Fetch crop path + sensor values + label via cleaned_daily_readings
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
    print(f"  Fetched {len(df)} crop records")

    # Verify files on disk
    print("🔍 Verifying image files on disk...")
    def is_accessible(path):
        try:
            with open(path, 'rb') as f:
                f.read(1)
            return True
        except:
            return False
    tqdm.pandas(desc="Checking files")
    df['exists'] = df['image_path'].progress_apply(is_accessible)
    missing = (~df['exists']).sum()
    if missing:
        print(f"⚠️  {missing} inaccessible files removed.")
    df = df[df['exists']].drop(columns=['exists']).reset_index(drop=True)

    print(f"✅ {len(df)} images found.")

    # Normalize sensor values to [0, 1]
    for col, (lo, hi) in SENSOR_NORM.items():
        df[col] = (df[col].clip(lo, hi) - lo) / (hi - lo)

    # Map labels to target values
    targets = df['bucket_label'].map(CONCENTRATION_MAP)
    df['npk_val']   = [t[0] for t in targets]
    df['micro_val'] = [t[1] for t in targets]

    # Compute sample weights to handle class imbalance
    counts     = df['bucket_label'].value_counts()
    n_total    = len(df)
    n_classes  = len(counts)
    weight_map = {label: n_total / (n_classes * count) for label, count in counts.items()}
    df['sample_weight'] = df['bucket_label'].map(weight_map)

    print("\nDistribution by Bucket:")
    print(counts)
    print("\nSample Weights:")
    for label, w in weight_map.items():
        print(f"  {label}: {w:.4f}")

    return df

# ==========================================
# 2. CUSTOM DATA GENERATOR (MULTI-MODAL)
# ==========================================
class MultiModalGenerator(tf.keras.utils.Sequence):
    """
    Yields ([image_batch, sensor_batch], label_batch, weight_batch) per step.
    Augmentation applied to images during training.
    """
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
        img = tf.io.read_file(path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, self.img_size)
        img = tf.cast(img, tf.float32) / 255.0
        if self.augment:
            img = tf.image.random_flip_left_right(img)
            img = tf.image.random_brightness(img, 0.2)
            img = tf.image.random_contrast(img, 0.8, 1.2)
            img = tf.clip_by_value(img, 0.0, 1.0)
        return img.numpy()

    def __getitem__(self, idx):
        batch_idx = self.indices[idx * self.batch_size:(idx + 1) * self.batch_size]
        batch     = self.df.iloc[batch_idx]

        images  = np.array([self._load_image(p) for p in batch['image_path']])
        sensors = batch[['ph', 'ec', 'water_temp']].values.astype(np.float32)
        labels  = batch[['npk_val', 'micro_val']].values.astype(np.float32)
        weights = batch['sample_weight'].values.astype(np.float32)

        return (images, sensors), labels, weights

def create_generators(df):
    split = int(len(df) * 0.8)
    df_shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)
    train_df = df_shuffled.iloc[:split]
    val_df   = df_shuffled.iloc[split:]

    train_gen = MultiModalGenerator(train_df, BATCH_SIZE, IMG_SIZE, augment=True)
    val_gen   = MultiModalGenerator(val_df,   BATCH_SIZE, IMG_SIZE, augment=False)

    print(f"  Train: {len(train_df)} samples | Val: {len(val_df)} samples")
    return train_gen, val_gen

# ==========================================
# 3. MULTI-MODAL MODEL ARCHITECTURE
# ==========================================
def build_model():
    # --- Image branch (MobileNetV2) ---
    base_model = MobileNetV2(
        weights='imagenet',
        include_top=False,
        input_shape=(IMG_SIZE[0], IMG_SIZE[1], 3)
    )
    base_model.trainable = False

    img_input = base_model.input
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    x = Dense(256, activation='relu')(x)
    x = Dropout(0.4)(x)
    x = Dense(128, activation='relu')(x)

    # --- Sensor branch (ph, ec, water_temp) ---
    sensor_input = Input(shape=(3,), name='sensor_input')
    s = Dense(32, activation='relu')(sensor_input)
    s = BatchNormalization()(s)
    s = Dense(16, activation='relu')(s)

    # --- Merge ---
    merged = Concatenate()([x, s])
    merged = Dense(128, activation='relu')(merged)
    merged = Dropout(0.3)(merged)
    output = Dense(2, activation='linear')(merged)

    model = Model(inputs=[img_input, sensor_input], outputs=output)
    model.compile(
        optimizer=Adam(learning_rate=0.0005),
        loss='mse',
        metrics=['mae']
    )

    return model, base_model

def finetune_model(model, base_model):
    # Unfreeze top FINETUNE_LAYERS layers of MobileNetV2
    base_model.trainable = True
    for layer in base_model.layers[:-FINETUNE_LAYERS]:
        layer.trainable = False

    trainable = sum(1 for l in base_model.layers if l.trainable)
    print(f"  MobileNetV2 trainable layers: {trainable} / {len(base_model.layers)}")

    # Lower learning rate to avoid destroying learned weights
    model.compile(
        optimizer=Adam(learning_rate=1e-5),
        loss='mse',
        metrics=['mae']
    )
    return model

# ==========================================
# 4. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    df = get_dataset()

    if df.empty:
        print("❌ No data found.")
    else:
        print("\n🔀 Creating generators...")
        train_gen, val_gen = create_generators(df)

        print("🧠 Building Multi-Modal Model...")
        model, base_model = build_model()
        model.summary()

        # ── Phase 1: Train with frozen MobileNetV2 ──────────────
        print(f"\n🚀 Phase 1 — Training custom head ({EPOCHS_PHASE1} epochs, lr=5e-4)...")
        history_p1 = model.fit(
            train_gen,
            validation_data=val_gen,
            epochs=EPOCHS_PHASE1
        )

        # ── Phase 2: Fine-tune top MobileNetV2 layers ───────────
        print(f"\n🔓 Phase 2 — Fine-tuning top {FINETUNE_LAYERS} MobileNetV2 layers ({EPOCHS_PHASE2} epochs, lr=1e-5)...")
        model = finetune_model(model, base_model)
        history_p2 = model.fit(
            train_gen,
            validation_data=val_gen,
            epochs=EPOCHS_PHASE2
        )

        model.save(MODEL_SAVE_PATH)
        print(f"\n✅ Model saved to {MODEL_SAVE_PATH}")

        # Print final metrics
        final_mae = history_p2.history['val_mae'][-1]
        print(f"   Final val MAE (phase 2): {final_mae:.4f}")

