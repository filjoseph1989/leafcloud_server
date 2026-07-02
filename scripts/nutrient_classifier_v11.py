# [STEP 1] Import standard Python and third-party libraries needed throughout this script.
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

# [STEP 2] Add the project root to Python's module search path so "from app.core..."
# imports work when running this script directly from the terminal.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# [STEP 3] Import project-specific config (only possible now that sys.path is patched above).
from app.core.config import settings

# [STEP 4] Set all top-level configuration constants used throughout training:
# DB connection, image size, batch size, output filename, sensor normalization ranges,
# and the four nutrient class labels with their integer index mapping.
DB_URL = settings.DATABASE_URL
IMG_SIZE = (224, 224)
BATCH_SIZE = 32 # kani gamit ni unsa kadaghan ang samples nga i-feed sa model kada training step. Mas dako nga batch size → mas stable ang gradient estimates pero mas taas ang memory usage.
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M')
MODEL_SAVE_PATH = f'leafcloud_multimodal_v11_{TIMESTAMP}.keras'

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 1.6),   # normalized range matching actual data limits
    'water_temp': (24.0, 29.0),
}

LABEL_LIST = ['Water', 'NPK', 'Micro', 'Mix']
LABEL_TO_IDX = {l: i for i, l in enumerate(LABEL_LIST)}


# Python reads and registers this function definition, but does NOT run its body yet.
def fetch_raw_data(engine) -> pd.DataFrame:
    # [STEP 9] Run a SQL JOIN across image_crops, cleaned_daily_readings, and experiments
    # to get every crop image path paired with its sensor readings and bucket label.
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


# Python reads and registers this function definition, but does NOT run its body yet.
def filter_missing_images(df: pd.DataFrame) -> pd.DataFrame:
    # [STEP 11] Verify every image file in the dataframe is actually readable on disk.
    # Rows whose files are missing or unreadable are dropped so training never hits a
    # file-not-found error mid-epoch.
    if df.empty:
        return df
    
    print('🔍 Verifying image files on disk...')

    # Kani kay function ni nga mag check kung ang path ba kay accessible (exists and readable). I-try open ang file, if successful return True, else False.
    def is_accessible(path):
        try:
            with open(path, 'rb') as f:
                f.read(1)
            return True
        except:
            return False

    # kani nga line magpagawas ni sa terminal ang progress bar samtang gi check ang files, gamit ang tqdm library.
    tqdm.pandas(desc='Checking files')

    # katong function nga `is_accessible`` kay tawagun diri.
    # para gamiton pag check isa-isa ang mga image paths sa dataframe, ug i-store ang results (True/False) sa new column nga 'exists'.
    df['exists'] = df['image_path'].progress_apply(is_accessible)
    
    # bilangon nato pila ka files ang na check, ug pila ang na mark as missing (exists=False). 
    # I-print nato ni sa terminal para mahibal-an kung unsa kadaghan ang problema sa missing files.
    missing = (~df['exists']).sum()
    if missing:
        print(f'⚠️  {missing} inaccessible files removed.')

    # i-filter nato ang dataframe para i-keep lang ang rows nga naay valid images (exists=True), 
    # unya i-drop nato ang 'exists' column kay wala na siya gamit after filtering. 
    # I-reset nato ang index para tidy ang dataframe before returning.
    return df[df['exists']].drop(columns=['exists']).reset_index(drop=True)


# Python reads and registers this function definition, but does NOT run its body yet.
def calculate_continuous_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates continuous targets for Macro and Micro scaling based on elapsed experiment time.
    Formula: ratio = 1.0 - (current_timestamp - start_timestamp) / total_experiment_duration
    This models depletion over time rather than relying directly on noisy/concentrating EC.
    """
    # [STEP 14] Parse timestamps and compute the start/end time of each experiment.
    # These bounds are used in STEP 15 to calculate how far along each reading is.
    print('\n📈 Calculating continuous time-based depletion targets (V11)...')

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    exp_time_bounds = {}
    for exp_id, group in df.groupby('experiment_id'):
        if len(group) > 0:
            min_ts = group['timestamp'].min()
            max_ts = group['timestamp'].max()
            exp_time_bounds[exp_id] = (min_ts, max_ts)

    print('  Experiment Durations:')
    for exp_id, (min_ts, max_ts) in exp_time_bounds.items():
        duration_days = (max_ts - min_ts).total_seconds() / (24 * 3600)
        print(f'    Experiment {exp_id}: duration={duration_days:.2f} days ({min_ts} to {max_ts})')

    macro_vals = []
    micro_vals = []

    # [STEP 15] For every row, compute a depletion ratio (1.0 at experiment start → 0.0 at end).
    # Water rows get 0.0 for both targets. NPK/Micro/Mix rows get their respective ratios.
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

            # Depletion ratio represents how much of the initial dose remains
            # Starts at 1.0 on day 1, decays linearly to 0.0 at the end of the experiment
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

    print('  Target calculation complete.')
    print(f"  Macro scale range: min={df['macro_val'].min():.2f}, max={df['macro_val'].max():.2f}, mean={df['macro_val'].mean():.2f}")
    print(f"  Micro scale range: min={df['micro_val'].min():.2f}, max={df['micro_val'].max():.2f}, mean={df['micro_val'].mean():.2f}")
    return df


# Python reads and registers this function definition, but does NOT run its body yet.
def apply_normalization(df: pd.DataFrame) -> pd.DataFrame:
    # [STEP 17] Clip each sensor column to its expected physical range, then scale to [0, 1]
    # using the (min, max) bounds in SENSOR_NORM so all inputs are on the same scale for training.
    for col, (lo, hi) in SENSOR_NORM.items():
        df[col] = (df[col].clip(lo, hi) - lo) / (hi - lo)
    return df


# Python reads and registers this function definition, but does NOT run its body yet.
def calculate_sample_weights(df: pd.DataFrame) -> pd.DataFrame:
    # [STEP 20] Compute per-sample weights inversely proportional to each class's frequency
    # so the majority class does not dominate training.
    counts = df['bucket_label'].value_counts()
    n_total = len(df)
    n_classes = len(counts)
    weight_map = {label: n_total / (n_classes * count) for label, count in counts.items()}
    df['sample_weight'] = df['bucket_label'].map(weight_map)
    return df


# Python reads and registers this function definition, but does NOT run its body yet.
def get_dataset():
    # [STEP 7] Connect sa database para maka run ta og mga query.
    print('🔌 Connecting to Database...')
    engine = create_engine(DB_URL)

    # [STEP 8] Call fetch_raw_data() — naa function naka define ani diri ra oud nga file, search lang
    df = fetch_raw_data(engine)

    # [STEP 10] Call filter_missing_images() — naa function naka define ani diri ra oud nga file, search lang
    df = filter_missing_images(df)

    # [STEP 12] If no valid images remain, return two empty DataFrames.
    if df.empty:
        return df, df

    print(f'✅ {len(df)} valid images found.')
    print('\nClass distribution:')
    print(df['bucket_label'].value_counts())

    # [STEP 13] Call calculate_continuous_targets() — naa function naka define ani diri ra oud nga file, search lang
    df = calculate_continuous_targets(df)

    # [STEP 16] calculate_continuous_targets() is done. Call apply_normalization() — jumps into that function body.
    df = apply_normalization(df)
    
    # [STEP 18] apply_normalization() is done. Map each string label to an integer index for one-hot encoding.
    df['label_idx'] = df['bucket_label'].map(LABEL_TO_IDX)

    # [STEP 19] Call calculate_sample_weights() — jumps into that function body now.
    df = calculate_sample_weights(df)

    # [STEP 21] calculate_sample_weights() is done. Perform a stratified 80/20 train/val split
    # so each class is proportionally represented in both sets, then return the two DataFrames.
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(splitter.split(df, df['label_idx']))
    train_df = df.iloc[train_idx].reset_index(drop=True)
    val_df = df.iloc[val_idx].reset_index(drop=True)

    print(f'\nTrain: {len(train_df)} | Val: {len(val_df)}')
    print('Val class distribution:')
    print(val_df['bucket_label'].value_counts())

    return train_df, val_df


# Python reads and registers this class definition, but does NOT instantiate it yet.
# __init__ is called at STEP 23. __len__, __getitem__, and on_epoch_end are called
# repeatedly by Keras during each model.fit() call in STEPs 33–35.
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


# Python reads and registers this class definition, but does NOT instantiate it yet.
# StopGradient.call() is invoked automatically by TensorFlow inside build_model_v11() at STEP 29.
@tf.keras.utils.register_keras_serializable(package="Custom")
class StopGradient(tf.keras.layers.Layer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def call(self, inputs):
        return tf.stop_gradient(inputs)

    def compute_output_shape(self, input_shape):
        return input_shape


# Python reads and registers this function definition, but does NOT run its body yet.
def build_model_v11():
    # [STEP 25] Load MobileNetV2 pre-trained on ImageNet with its classification head removed.
    # Frozen initially so Phase 1 only trains the new layers added on top.
    base_model = MobileNetV2(
        weights='imagenet',
        include_top=False,
        input_shape=(IMG_SIZE[0], IMG_SIZE[1], 3)
    )
    base_model.trainable = False

    # [STEP 26] Image feature branch: pool the MobileNetV2 spatial features down to a 256-d vector.
    img_input = base_model.input
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    x = Dense(256, activation='relu')(x)
    x = Dropout(0.4)(x)

    # [STEP 27] Sensor feature branch: two BN-normalised Dense layers compress the 3 sensor inputs
    # into a 32-d embedding that can be fused with the image features.
    sensor_input = Input(shape=(3,), name='sensor_input')
    s = Dense(64, activation='relu')(sensor_input)
    s = BatchNormalization()(s)
    s = Dense(64, activation='relu')(s)
    s = BatchNormalization()(s)
    s = Dense(32, activation='relu')(s)
    s = Dropout(0.2)(s)

    # ==========================================
    # PATH A: Classification branch (Shared backbone -> Custom Fusion)
    # ==========================================
    # [STEP 28] Concatenate image and sensor embeddings, pass through a shared Dense layer,
    # then split into a 4-class softmax output (Water / NPK / Micro / Mix).
    clf_merged = Concatenate()([x, s])
    clf_merged = Dense(256, activation='relu')(clf_merged)
    clf_merged = BatchNormalization()(clf_merged)
    clf_merged_dropout = Dropout(0.3)(clf_merged)

    clf_branch = Dense(64, activation='relu')(clf_merged_dropout)
    clf_branch = Dropout(0.2)(clf_branch)
    clf_output = Dense(4, activation='softmax', name='clf_output')(clf_branch)

    # ==========================================
    # PATH B: Conditioned Regression branch (Complete isolation)
    # ==========================================
    # [STEP 29] Stop gradients from the backbone outputs so regression loss cannot corrupt
    # the classification feature extractors. Then build an independent fusion path that also
    # receives the stopped classification output as a conditioning signal, ending in a
    # 2-output sigmoid (macro_val, micro_val) bounded to [0, 1].
    x_stopped = StopGradient()(x)
    s_stopped = StopGradient()(s)
    clf_output_stopped = StopGradient()(clf_output)

    reg_merged = Concatenate()([x_stopped, s_stopped, clf_output_stopped])
    reg_merged = Dense(256, activation='relu')(reg_merged)
    reg_merged = BatchNormalization()(reg_merged)
    reg_merged = Dense(128, activation='relu')(reg_merged)
    reg_merged_dropout = Dropout(0.3)(reg_merged)

    reg_branch = Dense(64, activation='relu')(reg_merged_dropout)
    reg_branch = Dense(32, activation='relu')(reg_branch)
    # Sigmoid limits outputs between [0.0, 1.0]
    reg_output = Dense(2, activation='sigmoid', name='reg_output')(reg_branch)

    # [STEP 30] Assemble the final Model with two inputs (image + sensor) and two outputs
    # (clf_output + reg_output), then return it alongside the base model handle.
    model = Model(inputs=[img_input, sensor_input], outputs=[clf_output, reg_output])
    return model, base_model


# [STEP 5] Python has finished reading the whole file. Now it hits this block and starts
# actual execution. This is the real entry point when you run:
#   python scripts/nutrient_classifier_v11.py
if __name__ == '__main__':
    # [STEP 6] Call get_dataset() — jumps up into that function body now.
    train_df, val_df = get_dataset()

    # [STEP 22] get_dataset() is done. If the result is empty, nothing to train — exit early.
    if train_df.empty:
        print('❌ No data found.')
    else:
        # [STEP 23] Instantiate data generators for training (with augmentation) and validation.
        # MultiModalGenerator.__init__ is called here; __getitem__ and on_epoch_end will be
        # called repeatedly by Keras during each model.fit() call below.
        train_gen = MultiModalGenerator(train_df, BATCH_SIZE, IMG_SIZE, augment=True)
        val_gen   = MultiModalGenerator(val_df,   BATCH_SIZE, IMG_SIZE, augment=False)

        # [STEP 24] Call build_model_v11() — jumps into that function body now.
        print('🧠 Building Multi-Task Multi-Modal Model (V11)...')
        model, base_model = build_model_v11()
        # [STEP 31] build_model_v11() is done. Print a layer-by-layer summary of the assembled model.
        model.summary()

        # [STEP 32] Define three callbacks that fire at the end of each epoch during fit():
        # • early_stop_clf   — stops Phase 1 if val classification accuracy stops improving (patience=10).
        # • early_stop_joint — stops Phase 2/3 if val regression MAE stops improving (patience=15).
        # • reduce_lr        — halves the learning rate if val loss plateaus for 5 epochs.
        early_stop_clf = EarlyStopping(
            monitor='val_clf_output_accuracy',
            patience=10,
            restore_best_weights=True,
            mode='max',
            verbose=1
        )

        # Monitors regression MAE to ensure the regression branch fully converges
        early_stop_joint = EarlyStopping(
            monitor='val_reg_output_mae',
            patience=15,
            restore_best_weights=True,
            mode='min',
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
        # [STEP 33] Compile with reg_weight=0.0 so only classification loss flows through.
        # This lets the shared backbone learn discriminative image features before the
        # regression branch is activated. Runs for up to 50 epochs.
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
        # [STEP 34] Re-compile with reg_weight=0.20 to activate the regression loss.
        # Both branches now train simultaneously while the MobileNet backbone stays frozen.
        print('\n🚀 Phase 2 Training (Joint — reg_weight=0.20)...')
        model.compile(
            optimizer=Adam(learning_rate=0.0005),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.20},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        model.fit(train_gen, validation_data=val_gen, epochs=40,
                  callbacks=[early_stop_joint, reduce_lr])

        # --------------------------------------------------
        # Phase 3: Fine-tune top MobileNet layers
        # --------------------------------------------------
        # [STEP 35] Unfreeze the top 30 MobileNet layers and re-compile at a much lower learning
        # rate (1e-5) so fine-tuning adjusts the pretrained weights gently without catastrophic
        # forgetting. All other settings match Phase 2.
        print('\n🔓 Phase 3 Fine-tuning (Top MobileNet Layers — reg_weight=0.20)...')
        base_model.trainable = True
        for layer in base_model.layers[:-30]:
            layer.trainable = False

        model.compile(
            optimizer=Adam(learning_rate=1e-5),
            loss={'clf_output': 'categorical_crossentropy', 'reg_output': 'mse'},
            loss_weights={'clf_output': 1.0, 'reg_output': 0.20},
            metrics={'clf_output': 'accuracy', 'reg_output': 'mae'}
        )
        model.fit(train_gen, validation_data=val_gen, epochs=30,
                  callbacks=[early_stop_joint, reduce_lr])

        # [STEP 36] Save the fully trained model to disk.
        model.save(MODEL_SAVE_PATH)
        print(f'\n✅ Model saved to {MODEL_SAVE_PATH}')
