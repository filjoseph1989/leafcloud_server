import os
import sys
import time
import platform

# -------------------------------------------------------------
# Early RAM Measurement (Baseline)
# -------------------------------------------------------------
def get_ram_usage_mb():
    """Get the current process RAM usage in Megabytes."""
    try:
        import resource
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == 'darwin':
            # On macOS, ru_maxrss is in bytes
            return rusage.ru_maxrss / (1024.0 * 1024.0)
        else:
            # On Linux/Unix, ru_maxrss is in kilobytes
            return rusage.ru_maxrss / 1024.0
    except Exception:
        return 0.0

baseline_ram = get_ram_usage_mb()

# -------------------------------------------------------------
# Heavy Imports
# -------------------------------------------------------------
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support, classification_report,
    confusion_matrix, mean_absolute_error, mean_squared_error, r2_score
)
from tqdm import tqdm

# Add project root to sys.path so 'app' module can be resolved
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.config import settings

# -------------------------------------------------------------
# Config / Constants
# -------------------------------------------------------------
DB_URL = settings.DATABASE_URL
IMG_SIZE = (224, 224)
BATCH_SIZE = 32

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 3.0),
    'water_temp': (24.0, 29.0),
}

LABEL_LIST = ['Water', 'NPK', 'Micro', 'Mix']
LABEL_TO_IDX = {l: i for i, l in enumerate(LABEL_LIST)}

CONCENTRATION_MAP = {
    'Water': [0.0, 0.0],
    'NPK':   [2.0, 0.0],
    'Micro': [0.0, 2.0],
    'Mix':   [2.0, 2.0],
}

def load_image(path):
    """Loads and preprocesses image crop to match training pipeline."""
    try:
        img_raw = tf.io.read_file(path)
        img = tf.image.decode_jpeg(img_raw, channels=3)
        img = tf.image.resize(img, IMG_SIZE)
        img = preprocess_input(img)
        return img.numpy()
    except Exception as e:
        return None

def get_validation_data():
    """Fetches, filters, normalizes, and splits validation dataset."""
    print("🔌 Connecting to Database...")
    engine = create_engine(DB_URL)
    
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
    print(f"  Fetched {len(df)} total crop records")

    # Replicate train split logic (shuffle with random_state 42, split 80/20)
    df_shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)
    split = int(len(df_shuffled) * 0.8)
    val_df = df_shuffled.iloc[split:].reset_index(drop=True)
    print(f"  Validation subset size: {len(val_df)}")
    
    # Verify accessible image files
    print("🔍 Verifying image files on disk for validation set...")
    valid_mask = []
    for idx, row in val_df.iterrows():
        try:
            with open(row['image_path'], 'rb') as f:
                f.read(1)
            valid_mask.append(True)
        except:
            valid_mask.append(False)
    
    val_df = val_df[valid_mask].reset_index(drop=True)
    print(f"✅ {len(val_df)} valid validation images found.")

    # Normalize sensor readings
    for col, (lo, hi) in SENSOR_NORM.items():
        val_df[col] = (val_df[col].clip(lo, hi) - lo) / (hi - lo)

    # Encode label index and regression targets
    val_df['label_idx'] = val_df['bucket_label'].map(LABEL_TO_IDX)
    targets = val_df['bucket_label'].map(CONCENTRATION_MAP)
    val_df['macro_val'] = [t[0] for t in targets]
    val_df['micro_val'] = [t[1] for t in targets]

    return val_df

def run_evaluation(model, val_df):
    """Loads validation images/sensors and runs model batch inference."""
    images = []
    sensors = []
    valid_indices = []

    print("🖼️  Loading and preprocessing validation images...")
    for idx, row in tqdm(val_df.iterrows(), total=len(val_df), desc="Loading images"):
        img = load_image(row['image_path'])
        if img is not None:
            images.append(img)
            sensors.append([row['ph'], row['ec'], row['water_temp']])
            valid_indices.append(idx)

    images = np.array(images)
    sensors = np.array(sensors, dtype=np.float32)
    synced_df = val_df.iloc[valid_indices].reset_index(drop=True)

    print(f"🧠 Running batch predictions on {len(synced_df)} samples...")
    preds = model.predict([images, sensors], batch_size=BATCH_SIZE, verbose=0)
    
    # Keras multi-output models return a list of outputs or dict
    if isinstance(preds, dict):
        clf_preds = preds['clf_output']
        reg_preds = preds['reg_output']
    else:
        clf_idx = model.output_names.index('clf_output') if 'clf_output' in model.output_names else 0
        reg_idx = model.output_names.index('reg_output') if 'reg_output' in model.output_names else 1
        clf_preds = preds[clf_idx]
        reg_preds = preds[reg_idx]

    return clf_preds, reg_preds, synced_df, images, sensors

def evaluate_classification(y_true_idx, clf_preds, export_dir="exports"):
    """Computes and prints classification metrics and plots confusion matrix."""
    y_pred_idx = np.argmax(clf_preds, axis=1)
    
    # Calculate metrics
    acc = accuracy_score(y_true_idx, y_pred_idx)
    precision, recall, f1, _ = precision_recall_fscore_support(y_true_idx, y_pred_idx, average='weighted')
    
    print("\n==================================================")
    print("1. CLASSIFICATION METRICS")
    print("==================================================")
    print(f"Overall Accuracy:  {acc:.4f} ({acc*100:.2f}%)")
    print(f"Weighted Precision: {precision:.4f}")
    print(f"Weighted Recall:    {recall:.4f}")
    print(f"Weighted F1-Score:  {f1:.4f}")
    
    print("\nDetailed Classification Report:")
    print(classification_report(y_true_idx, y_pred_idx, target_names=LABEL_LIST))
    
    # Confusion Matrix
    cm = confusion_matrix(y_true_idx, y_pred_idx)
    cm_df = pd.DataFrame(cm, index=LABEL_LIST, columns=LABEL_LIST)
    print("Confusion Matrix:")
    print(cm_df)

    # Plot Confusion Matrix Heatmap
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm_df, annot=True, fmt='d', cmap='Blues', cbar=False,
                annot_kws={"size": 14, "weight": "bold"})
    plt.title("Confusion Matrix - Nutrient Classification (V3)", fontsize=14, pad=15)
    plt.ylabel("Actual Label", fontsize=12)
    plt.xlabel("Predicted Label", fontsize=12)
    plt.tight_layout()
    
    # Save confusion matrix image
    os.makedirs(export_dir, exist_ok=True)
    save_path = os.path.join(export_dir, "confusion_matrix_v3.png")
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"\n📊 Saved confusion matrix heatmap to: {save_path}")

def evaluate_regression(y_true_reg, reg_preds):
    """Computes and prints regression metrics (MAE, RMSE, R2) overall and per target."""
    mae_overall = mean_absolute_error(y_true_reg, reg_preds)
    rmse_overall = np.sqrt(mean_squared_error(y_true_reg, reg_preds))
    r2_overall = r2_score(y_true_reg, reg_preds)

    # Target specific
    mae_macro = mean_absolute_error(y_true_reg[:, 0], reg_preds[:, 0])
    rmse_macro = np.sqrt(mean_squared_error(y_true_reg[:, 0], reg_preds[:, 0]))
    r2_macro = r2_score(y_true_reg[:, 0], reg_preds[:, 0])

    mae_micro = mean_absolute_error(y_true_reg[:, 1], reg_preds[:, 1])
    rmse_micro = np.sqrt(mean_squared_error(y_true_reg[:, 1], reg_preds[:, 1]))
    r2_micro = r2_score(y_true_reg[:, 1], reg_preds[:, 1])

    print("\n==================================================")
    print("2. REGRESSION METRICS (Nutrient Concentrations)")
    print("==================================================")
    print(f"Overall Regression:")
    print(f"  - Mean Absolute Error (MAE):          {mae_overall:.4f}")
    print(f"  - Root Mean Squared Error (RMSE):      {rmse_overall:.4f}")
    print(f"  - R-squared (R2) Variance Explained:   {r2_overall:.4f}")
    
    print(f"\nMacro Nutrient (NPK) Concentration:")
    print(f"  - MAE:  {mae_macro:.4f}")
    print(f"  - RMSE: {rmse_macro:.4f}")
    print(f"  - R2:   {r2_macro:.4f}")
    
    print(f"\nMicro Nutrient Concentration:")
    print(f"  - MAE:  {mae_micro:.4f}")
    print(f"  - RMSE: {rmse_micro:.4f}")
    print(f"  - R2:   {r2_micro:.4f}")

def profile_latency(model, images, sensors, max_samples=100):
    """Profiles single-sample inference latency using standard Keras predict and direct calls."""
    n_samples = min(len(images), max_samples)
    print(f"\n==================================================")
    print(f"3. DEPLOYMENT & HARDWARE METRICS (Profiling {n_samples} samples)")
    print("==================================================")
    
    # Method 1: Model direct call (highly optimized for single predictions)
    # Warmup
    _ = model([images[0:1], sensors[0:1]], training=False)
    
    direct_latencies = []
    for i in range(n_samples):
        img_batch = images[i:i+1]
        sens_batch = sensors[i:i+1]
        
        t0 = time.perf_counter()
        _ = model([img_batch, sens_batch], training=False)
        t1 = time.perf_counter()
        direct_latencies.append((t1 - t0) * 1000.0) # in ms

    # Method 2: Model predict call
    predict_latencies = []
    for i in range(min(n_samples, 20)): # Limit predict latency evaluation as it is much slower
        img_batch = images[i:i+1]
        sens_batch = sensors[i:i+1]
        
        t0 = time.perf_counter()
        _ = model.predict([img_batch, sens_batch], batch_size=1, verbose=0)
        t1 = time.perf_counter()
        predict_latencies.append((t1 - t0) * 1000.0)

    print("\nInference Latency (Direct Call - model([img, sens], training=False)):")
    print(f"  - Average Latency: {np.mean(direct_latencies):.2f} ms")
    print(f"  - Median Latency:  {np.median(direct_latencies):.2f} ms")
    print(f"  - Min Latency:     {np.min(direct_latencies):.2f} ms")
    print(f"  - Max Latency:     {np.max(direct_latencies):.2f} ms")
    print(f"  - 90th Percentile: {np.percentile(direct_latencies, 90):.2f} ms")
    print(f"  - 95th Percentile: {np.percentile(direct_latencies, 95):.2f} ms")
    print(f"  - 99th Percentile: {np.percentile(direct_latencies, 99):.2f} ms")

    if predict_latencies:
        print("\nInference Latency (Standard Keras Predict - model.predict(...)):")
        print(f"  - Average Latency: {np.mean(predict_latencies):.2f} ms")
        print(f"  - Median Latency:  {np.median(predict_latencies):.2f} ms")

def print_memory_metrics(model_path, post_import_ram, post_load_ram, post_inf_ram):
    """Computes and prints model file size and RAM footprints."""
    # Model size on disk
    file_size_mb = os.path.getsize(model_path) / (1024.0 * 1024.0)
    
    # RAM increments
    import_overhead = post_import_ram - baseline_ram
    load_overhead = post_load_ram - post_import_ram
    inference_overhead = post_inf_ram - post_load_ram
    
    print("\nMemory & Footprint Metrics:")
    print(f"  - Model File Size:       {file_size_mb:.2f} MB")
    print(f"  - Baseline RAM (init):   {baseline_ram:.2f} MB")
    print(f"  - RAM after imports:     {post_import_ram:.2f} MB (+{import_overhead:.2f} MB)")
    print(f"  - RAM after model load:  {post_load_ram:.2f} MB (+{load_overhead:.2f} MB model overhead)")
    print(f"  - Peak RAM (inference):  {post_inf_ram:.2f} MB (+{inference_overhead:.2f} MB run overhead)")
    print("==================================================")

def main():
    # Record RAM after import (since main runs after module loading imports)
    post_import_ram = get_ram_usage_mb()

    # Determine Model path
    default_model = "leafcloud_multimodal_v3_20260520_1920.keras"
    model_path = sys.argv[1] if len(sys.argv) > 1 else default_model
    
    if not os.path.exists(model_path):
        # Fall back to searching for latest model in directory matching pattern
        import glob
        keras_files = glob.glob("leafcloud_multimodal_v3_*.keras")
        if keras_files:
            keras_files.sort(reverse=True)
            model_path = keras_files[0]
            print(f"ℹ️ Specified model not found. Using most recent: {model_path}")
        else:
            print(f"❌ ERROR: Model file not found: {model_path}")
            sys.exit(1)

    print(f"💾 Loading model: {model_path} ...")
    model = tf.keras.models.load_model(model_path)
    post_load_ram = get_ram_usage_mb()

    # Fetch and prepare validation dataset
    val_df = get_validation_data()
    if val_df.empty:
        print("❌ ERROR: Validation dataset is empty!")
        sys.exit(1)

    # Run predictions
    clf_preds, reg_preds, synced_df, images, sensors = run_evaluation(model, val_df)
    post_inf_ram = get_ram_usage_mb()

    # Get true targets
    y_true_idx = synced_df['label_idx'].values
    y_true_reg = synced_df[['macro_val', 'micro_val']].values

    # Evaluate
    evaluate_classification(y_true_idx, clf_preds)
    evaluate_regression(y_true_reg, reg_preds)
    profile_latency(model, images, sensors)
    print_memory_metrics(model_path, post_import_ram, post_load_ram, post_inf_ram)

if __name__ == "__main__":
    main()
