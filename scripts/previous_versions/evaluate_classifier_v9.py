import os
import sys
import time

def get_ram_usage_mb():
    try:
        import resource
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == 'darwin':
            return rusage.ru_maxrss / (1024.0 * 1024.0)
        else:
            return rusage.ru_maxrss / 1024.0
    except Exception:
        return 0.0

baseline_ram = get_ram_usage_mb()

import numpy as np
import pandas as pd
import tensorflow as tf
import builtins
builtins.tf = tf
tf.keras.layers.Lambda.compute_output_shape = lambda self, input_shape: input_shape
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support, classification_report,
    confusion_matrix, mean_absolute_error, mean_squared_error, r2_score
)
from tqdm import tqdm

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.config import settings

# -------------------------------------------------------------
# Config
# -------------------------------------------------------------
DB_URL = settings.DATABASE_URL
IMG_SIZE = (224, 224)
BATCH_SIZE = 32

@tf.keras.utils.register_keras_serializable(package="Custom")
class StopGradient(tf.keras.layers.Layer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def call(self, inputs):
        return tf.stop_gradient(inputs)

    def compute_output_shape(self, input_shape):
        return input_shape

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 1.6),   # normalized range matching actual data limits
    'water_temp': (24.0, 29.0),
}

LABEL_LIST = ['Water', 'NPK', 'Micro', 'Mix']
LABEL_TO_IDX = {l: i for i, l in enumerate(LABEL_LIST)}


def load_image(path):
    try:
        img_raw = tf.io.read_file(path)
        img = tf.image.decode_jpeg(img_raw, channels=3)
        img = tf.image.resize(img, IMG_SIZE)
        img = preprocess_input(img)
        return img.numpy()
    except Exception:
        return None


def calculate_continuous_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates continuous targets for Macro and Micro scaling based on elapsed experiment time.
    Formula: ratio = 1.0 - (current_timestamp - start_timestamp) / total_experiment_duration
    This models depletion over time rather than relying directly on noisy/concentrating EC.
    """
    print('\n📈 Calculating continuous time-based depletion targets (V9)...')
    
    # Ensure timestamps are parsed as datetimes
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # 1. Compute start and end timestamps per experiment
    exp_time_bounds = {}
    for exp_id, group in df.groupby('experiment_id'):
        if len(group) > 0:
            min_ts = group['timestamp'].min()
            max_ts = group['timestamp'].max()
            exp_time_bounds[exp_id] = (min_ts, max_ts)

    macro_vals = []
    micro_vals = []

    # 2. Calculate time-based ratio based on bucket labels
    for idx, row in df.iterrows():
        label = row['bucket_label']
        exp_id = row['experiment_id']
        ts = row['timestamp']

        if label == 'Water':
            macro_vals.append(0.0)
            micro_vals.append(0.0)
        else:
            min_ts, max_ts = exp_time_bounds.get(exp_id, (ts, ts))
            duration_sec = (max_ts - min_ts).total_seconds()
            elapsed_sec = (ts - min_ts).total_seconds()
            
            time_ratio = elapsed_sec / duration_sec if duration_sec > 0.0 else 0.0
            ratio = float(np.clip(1.0 - time_ratio, 0.0, 1.0))

            if label == 'NPK':
                macro_vals.append(ratio)
                micro_vals.append(0.0)
            elif label == 'Micro':
                macro_vals.append(0.0)
                micro_vals.append(ratio)
            elif label == 'Mix':
                macro_vals.append(ratio)
                micro_vals.append(ratio)

    df['macro_val'] = macro_vals
    df['micro_val'] = micro_vals
    return df


def get_validation_data():
    print("🔌 Connecting to Database...")
    engine = create_engine(DB_URL)

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
    print(f"  Fetched {len(df)} total crop records")

    # Calculate continuous regression targets on full dataframe
    df = calculate_continuous_targets(df)

    df['label_idx'] = df['bucket_label'].map(LABEL_TO_IDX)
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    _, val_idx = next(splitter.split(df, df['label_idx']))
    val_df = df.iloc[val_idx].reset_index(drop=True)
    print(f"  Validation subset size: {len(val_df)}")

    print("🔍 Verifying image files on disk...")
    valid_mask = []
    for _, row in val_df.iterrows():
        try:
            with open(row['image_path'], 'rb') as f:
                f.read(1)
            valid_mask.append(True)
        except:
            valid_mask.append(False)

    val_df = val_df[valid_mask].reset_index(drop=True)
    print(f"✅ {len(val_df)} valid validation images found.")
    print('\nVal class distribution:')
    print(val_df['bucket_label'].value_counts())

    for col, (lo, hi) in SENSOR_NORM.items():
        val_df[col] = (val_df[col].clip(lo, hi) - lo) / (hi - lo)

    return val_df


def run_evaluation(model, val_df):
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

    if isinstance(preds, dict):
        clf_preds = preds['clf_output']
        reg_preds = preds['reg_output']
    else:
        clf_idx = model.output_names.index('clf_output') if 'clf_output' in model.output_names else 0
        reg_idx = model.output_names.index('reg_output') if 'reg_output' in model.output_names else 1
        clf_preds = preds[clf_idx]
        reg_preds = preds[reg_idx]

    return clf_preds, reg_preds, synced_df, images, sensors


def evaluate_classification(y_true_idx, clf_preds, export_dir):
    y_pred_idx = np.argmax(clf_preds, axis=1)

    acc = accuracy_score(y_true_idx, y_pred_idx)
    precision, recall, f1, _ = precision_recall_fscore_support(y_true_idx, y_pred_idx, average='weighted')

    print("\n==================================================")
    print("1. CLASSIFICATION METRICS")
    print("==================================================")
    print(f"Overall Accuracy:   {acc:.4f} ({acc*100:.2f}%)")
    print(f"Weighted Precision: {precision:.4f}")
    print(f"Weighted Recall:    {recall:.4f}")
    print(f"Weighted F1-Score:  {f1:.4f}")
    print("\nDetailed Classification Report:")
    print(classification_report(y_true_idx, y_pred_idx, target_names=LABEL_LIST))

    cm = confusion_matrix(y_true_idx, y_pred_idx)
    cm_df = pd.DataFrame(cm, index=LABEL_LIST, columns=LABEL_LIST)
    print("Confusion Matrix:")
    print(cm_df)

    plt.figure(figsize=(8, 6))
    sns.heatmap(cm_df, annot=True, fmt='d', cmap='Blues', cbar=False,
                annot_kws={"size": 14, "weight": "bold"})
    plt.title("Confusion Matrix - Nutrient Classification (V9)", fontsize=14, pad=15)
    plt.ylabel("Actual Label", fontsize=12)
    plt.xlabel("Predicted Label", fontsize=12)
    plt.tight_layout()

    os.makedirs(export_dir, exist_ok=True)
    save_path = os.path.join(export_dir, "confusion_matrix_v9.png")
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"\n📊 Saved confusion matrix heatmap to: {save_path}")

    return acc, precision, recall, f1


def evaluate_regression(y_true_reg, reg_preds, synced_df):
    mae_overall  = mean_absolute_error(y_true_reg, reg_preds)
    rmse_overall = np.sqrt(mean_squared_error(y_true_reg, reg_preds))
    r2_overall   = r2_score(y_true_reg, reg_preds)

    mae_macro  = mean_absolute_error(y_true_reg[:, 0], reg_preds[:, 0])
    rmse_macro = np.sqrt(mean_squared_error(y_true_reg[:, 0], reg_preds[:, 0]))
    r2_macro   = r2_score(y_true_reg[:, 0], reg_preds[:, 0])

    mae_micro  = mean_absolute_error(y_true_reg[:, 1], reg_preds[:, 1])
    rmse_micro = np.sqrt(mean_squared_error(y_true_reg[:, 1], reg_preds[:, 1]))
    r2_micro   = r2_score(y_true_reg[:, 1], reg_preds[:, 1])

    print("\n==================================================")
    print("2. REGRESSION METRICS (Continuous Concentrations)")
    print("==================================================")
    print(f"Overall Regression:")
    print(f"  - Mean Absolute Error (MAE):         {mae_overall:.4f}")
    print(f"  - Root Mean Squared Error (RMSE):     {rmse_overall:.4f}")
    print(f"  - R-squared (R2) Variance Explained:  {r2_overall:.4f}")

    print(f"\nMacro Nutrient (NPK) Concentration:")
    print(f"  - MAE:  {mae_macro:.4f}")
    print(f"  - RMSE: {rmse_macro:.4f}")
    print(f"  - R2:   {r2_macro:.4f}")

    print(f"\nMicro Nutrient Concentration:")
    print(f"  - MAE:  {mae_micro:.4f}")
    print(f"  - RMSE: {rmse_micro:.4f}")
    print(f"  - R2:   {r2_micro:.4f}")

    print("\nPer-Class Regression Breakdown:")
    print(f"  {'Class':<8}  {'Macro (pred avg)':>16}  {'Micro (pred avg)':>16}  {'Macro (true avg)':>16}  {'Micro (true avg)':>16}")
    for label in LABEL_LIST:
        mask = synced_df['bucket_label'] == label
        if mask.sum() == 0:
            continue
        m_pred = reg_preds[mask, 0].mean()
        u_pred = reg_preds[mask, 1].mean()
        m_true = y_true_reg[mask, 0].mean()
        u_true = y_true_reg[mask, 1].mean()
        print(f"  {label:<8}  {m_pred:>16.4f}  {u_pred:>16.4f}  {m_true:>16.4f}  {u_true:>16.4f}")

    print(f"\nRegression Output Range:")
    print(f"  Macro — min: {reg_preds[:, 0].min():.4f}  max: {reg_preds[:, 0].max():.4f}")
    print(f"  Micro — min: {reg_preds[:, 1].min():.4f}  max: {reg_preds[:, 1].max():.4f}")


def profile_latency(model, images, sensors, max_samples=100):
    n_samples = min(len(images), max_samples)
    print(f"\n==================================================")
    print(f"3. DEPLOYMENT & HARDWARE METRICS (Profiling {n_samples} samples)")
    print("==================================================")

    # Warm-up inference
    _ = model([images[0:1], sensors[0:1]], training=False)

    direct_latencies = []
    for i in range(n_samples):
        t0 = time.perf_counter()
        _ = model([images[i:i+1], sensors[i:i+1]], training=False)
        t1 = time.perf_counter()
        direct_latencies.append((t1 - t0) * 1000.0)

    predict_latencies = []
    for i in range(min(n_samples, 20)):
        t0 = time.perf_counter()
        _ = model.predict([images[i:i+1], sensors[i:i+1]], batch_size=1, verbose=0)
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
    file_size_mb = os.path.getsize(model_path) / (1024.0 * 1024.0)
    import_overhead    = post_import_ram - baseline_ram
    load_overhead      = post_load_ram - post_import_ram
    inference_overhead = post_inf_ram - post_load_ram

    print("\nMemory & Footprint Metrics:")
    print(f"  - Model File Size:       {file_size_mb:.2f} MB")
    print(f"  - Baseline RAM (init):   {baseline_ram:.2f} MB")
    print(f"  - RAM after imports:     {post_import_ram:.2f} MB (+{import_overhead:.2f} MB)")
    print(f"  - RAM after model load:  {post_load_ram:.2f} MB (+{load_overhead:.2f} MB model overhead)")
    print(f"  - Peak RAM (inference):  {post_inf_ram:.2f} MB (+{inference_overhead:.2f} MB run overhead)")
    print("==================================================")


def main():
    post_import_ram = get_ram_usage_mb()

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if args:
        model_path = args[0]
    else:
        import glob
        keras_files = sorted(glob.glob('leafcloud_multimodal_v9_*.keras'), reverse=True)
        if not keras_files:
            keras_files = sorted(glob.glob('leafcloud_multimodal_v8_*.keras'), reverse=True)
        if not keras_files:
            keras_files = sorted(glob.glob('leafcloud_multimodal_v7_*.keras'), reverse=True)
        if not keras_files:
            keras_files = sorted(glob.glob('leafcloud_multimodal_v6_*.keras'), reverse=True)
        if not keras_files:
            keras_files = sorted(glob.glob('leafcloud_multimodal_*.keras'), reverse=True)
        if not keras_files:
            print("❌ ERROR: No model file found.")
            sys.exit(1)
        model_path = keras_files[0]
        print(f"ℹ️ Using most recent model: {model_path}")

    if not os.path.exists(model_path):
        print(f"❌ ERROR: Model file not found: {model_path}")
        sys.exit(1)

    print(f"💾 Loading model: {model_path}...")
    model = tf.keras.models.load_model(model_path, safe_mode=False, custom_objects={'StopGradient': StopGradient})
    post_load_ram = get_ram_usage_mb()

    val_df = get_validation_data()
    if val_df.empty:
        print("❌ ERROR: Validation dataset is empty!")
        sys.exit(1)

    clf_preds, reg_preds, synced_df, images, sensors = run_evaluation(model, val_df)
    post_inf_ram = get_ram_usage_mb()

    y_true_idx = synced_df['label_idx'].values
    y_true_reg = synced_df[['macro_val', 'micro_val']].values

    evaluate_classification(y_true_idx, clf_preds, export_dir='exports')
    evaluate_regression(y_true_reg, reg_preds, synced_df)
    profile_latency(model, images, sensors)
    print_memory_metrics(model_path, post_import_ram, post_load_ram, post_inf_ram)


if __name__ == "__main__":
    main()
