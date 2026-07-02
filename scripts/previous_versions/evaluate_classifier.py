import os
import sys
import numpy as np
import pandas as pd
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    mean_squared_error, r2_score
)
from tqdm import tqdm
from app.core.config import settings

# ==========================================
# CONFIGURATION
# ==========================================
DB_URL        = settings.DATABASE_URL
IMG_SIZE      = (224, 224)
BATCH_SIZE    = 32
RANDOM_STATE  = 42
VAL_SPLIT     = 0.8

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 3.0),
    'water_temp': (24.0, 29.0),
}

# Mapping for 4-class classification (Must match nutrient_classifier.py)
LABELS = ['Water', 'NPK', 'Micro', 'Mix']

# ==========================================
# HELPERS
# ==========================================

def pred_to_class_v2(predictions):
    """Convert softmax output to bucket label by taking the argmax."""
    # predictions shape: (N, 4)
    indices = np.argmax(predictions, axis=1)
    return np.array([LABELS[i] for i in indices])

def load_and_normalize(df):
    for col, (lo, hi) in SENSOR_NORM.items():
        df[col] = (df[col].clip(lo, hi) - lo) / (hi - lo)
    return df

def load_image(path):
    try:
        img = tf.io.read_file(path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, IMG_SIZE)
        
        # Match MobileNetV2 preprocessing from train_v4
        # preprocess_input expects 0-255, outputs -1 to 1
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
        img = preprocess_input(img)
        return img.numpy()
    except Exception as e:
        return None

def get_val_df():
    engine = create_engine(DB_URL)
    query = """
    SELECT ic.crop_path AS image_path, cdr.ph, cdr.ec, cdr.water_temp, e.bucket_label
    FROM image_crops ic
    JOIN cleaned_daily_readings cdr ON ic.daily_reading_id = cdr.id
    JOIN experiments e ON cdr.experiment_id = e.id
    WHERE e.bucket_label IN ('NPK', 'Micro', 'Mix', 'Water')
    """
    df = pd.read_sql(query, engine)
    # Match the split logic from train_v4
    df_shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)
    split = int(len(df_shuffled) * VAL_SPLIT)
    val_df = df_shuffled.iloc[split:].reset_index(drop=True)
    return val_df

def run_predictions(model, df):
    print(f"Running predictions on {len(df)} samples...")
    images = []
    sensors = []
    valid_indices = []

    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Loading data"):
        img = load_image(row['image_path'])
        if img is not None:
            images.append(img)
            sensors.append([row['ph'], row['ec'], row['water_temp']])
            valid_indices.append(idx)

    images = np.array(images)
    sensors = np.array(sensors, dtype=np.float32)

    # Multi-modal input: (images, sensors)
    preds = model.predict([images, sensors], batch_size=BATCH_SIZE)
    return preds, df.iloc[valid_indices].reset_index(drop=True)

def print_metrics(y_true, y_pred_classes):
    print("\n" + "="*50)
    print("CLASSIFICATION REPORT")
    print("="*50)
    print(classification_report(y_true, y_pred_classes, target_names=LABELS, labels=LABELS))

    print("\n" + "="*50)
    print("CONFUSION MATRIX")
    print("="*50)
    cm = confusion_matrix(y_true, y_pred_classes, labels=LABELS)
    cm_df = pd.DataFrame(cm, index=LABELS, columns=LABELS)
    print(cm_df)

if __name__ == "__main__":
    MODEL_PATH = sys.argv[1] if len(sys.argv) > 1 else os.getenv("AI_MODEL_PATH", "leafcloud_sensor_boost_20260515_1930.keras")

    if not os.path.exists(MODEL_PATH):
        print(f"ERROR: Model file not found: {MODEL_PATH}")
        sys.exit(1)

    print(f"Loading model: {MODEL_PATH}")
    # Load model with potentially custom layers or compiled state
    model = tf.keras.models.load_model(MODEL_PATH)

    val_df = get_val_df()
    # Normalize sensors
    val_df = load_and_normalize(val_df)

    preds, synced_df = run_predictions(model, val_df)
    y_pred_classes = pred_to_class_v2(preds)
    y_true = synced_df['bucket_label'].values

    print_metrics(y_true, y_pred_classes)
