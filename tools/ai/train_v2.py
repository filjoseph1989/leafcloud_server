import os
import shutil
from datetime import datetime
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.layers import Dense, GlobalAveragePooling2D, Dropout
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from sqlalchemy import create_engine
from tqdm import tqdm

# ==========================================
# CONFIGURATION
# ==========================================
DB_URL = os.getenv("DATABASE_URL", "postgresql://fil:@localhost/leafcloud2")
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 15
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")
MODEL_SAVE_PATH = f"leafcloud_regression_model_{TIMESTAMP}.keras"
LOCAL_DATA_DIR = "/Users/fil/.gemini/tmp/leafcloud_training_data"

# Mapping bucket labels to [NPK_ml_L, Micro_ml_L]
CONCENTRATION_MAP = {
    'Water': [0.0, 0.0],
    'NPK':   [2.0, 0.0],
    'Micro': [0.0, 2.0],
    'Mix':   [2.0, 2.0]
}

# ==========================================
# 1. DATA LOADING & MAPPING
# ==========================================
def get_dataset():
    """
    Fetches image paths, verifies them, copies to local storage, and maps labels.
    """
    print("🔌 Connecting to Database leafcloud2...")
    engine = create_engine(DB_URL)

    query = """
    SELECT ic.crop_path as image_path, e.bucket_label
    FROM image_crops ic
    JOIN daily_readings dr ON ic.daily_reading_id = dr.id
    JOIN experiments e ON dr.experiment_id = e.id
    WHERE e.bucket_label IN ('NPK', 'Micro', 'Mix', 'Water')
    """
    df = pd.read_sql(query, engine)

    # Filter out missing or inaccessible files (e.g., Stale NFS handles)
    print("🔍 Verifying image files on disk...")
    def is_file_accessible(path):
        try:
            with open(path, 'rb') as f:
                f.read(1)
            return True
        except:
            return False

    tqdm.pandas(desc="Checking files")
    df['exists'] = df['image_path'].progress_apply(is_file_accessible)
    
    missing_count = len(df) - df['exists'].sum()
    if missing_count > 0:
        print(f"⚠️ Warning: {missing_count} images were not found or are inaccessible. Removing.")
    
    df = df[df['exists']].drop(columns=['exists']).reset_index(drop=True)

    # Copy images to local storage to bypass NFS issues
    print(f"📦 Copying {len(df)} images to local storage {LOCAL_DATA_DIR}...")
    if os.path.exists(LOCAL_DATA_DIR):
        shutil.rmtree(LOCAL_DATA_DIR)
    os.makedirs(LOCAL_DATA_DIR, exist_ok=True)

    local_paths = []
    for i, row in tqdm(df.iterrows(), total=len(df), desc="Copying"):
        src = row['image_path']
        unique_name = f"{i}_{os.path.basename(src)}"
        dst = os.path.join(LOCAL_DATA_DIR, unique_name)
        try:
            shutil.copy2(src, dst)
            local_paths.append(dst)
        except:
            local_paths.append(None)
            
    df['image_path'] = local_paths
    df = df.dropna(subset=['image_path'])

    print(f"✅ Local Data Ready: {len(df)} images copied.")

    # Map labels to multiple target columns
    print("Mapping labels to concentrations...")
    targets = df['bucket_label'].map(CONCENTRATION_MAP)
    df['npk_val'] = [t[0] for t in targets]
    df['micro_val'] = [t[1] for t in targets]
    
    print("Distribution by Bucket:")
    print(df['bucket_label'].value_counts())
    
    return df

# ==========================================
# 2. DATA GENERATOR (REGRESSION)
# ==========================================
def create_generators(df):
    """
    Creates Keras Data Generators for Regression using local paths.
    """
    datagen = ImageDataGenerator(
        rescale=1./255,
        rotation_range=20,
        width_shift_range=0.15,
        height_shift_range=0.15,
        horizontal_flip=True,
        brightness_range=[0.8, 1.2],
        validation_split=0.2
    )

    y_cols = ['npk_val', 'micro_val']

    train_gen = datagen.flow_from_dataframe(
        dataframe=df,
        x_col="image_path",
        y_col=y_cols,
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode="raw",
        subset='training'
    )

    val_gen = datagen.flow_from_dataframe(
        dataframe=df,
        x_col="image_path",
        y_col=y_cols,
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode="raw",
        subset='validation'
    )

    return train_gen, val_gen

# ==========================================
# 3. MODEL ARCHITECTURE
# ==========================================
def build_model():
    """
    Builds MobileNetV2 with a Regression Head (2 outputs).
    """
    base_model = MobileNetV2(
        weights='imagenet',
        include_top=False,
        input_shape=(IMG_SIZE[0], IMG_SIZE[1], 3)
    )
    base_model.trainable = False

    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    x = Dense(256, activation='relu')(x)
    x = Dropout(0.4)(x)
    x = Dense(128, activation='relu')(x)
    
    # Final layer: 2 neurons (NPK and Micro)
    predictions = Dense(2, activation='linear')(x)

    model = Model(inputs=base_model.input, outputs=predictions)

    model.compile(
        optimizer=Adam(learning_rate=0.0005),
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
        print("❌ Error: No data found.")
    else:
        train_gen, val_gen = create_generators(df)

        print("🧠 Building Regression Model...")
        model = build_model()
        
        print("🚀 Starting Training...")
        history = model.fit(
            train_gen,
            validation_data=val_gen,
            epochs=EPOCHS
        )

        model.save(MODEL_SAVE_PATH)
        print(f"✅ Model saved to {MODEL_SAVE_PATH}")
        
        # Cleanup local images after training (Optional)
        # shutil.rmtree(LOCAL_DATA_DIR)
