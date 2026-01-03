import os
import numpy as np
import pandas as pd
try:
    import tensorflow as tf
    from tensorflow.keras.applications import MobileNetV2
    from tensorflow.keras.layers import Dense, GlobalAveragePooling2D, Dropout
    from tensorflow.keras.models import Model
    from tensorflow.keras.optimizers import Adam
    from tensorflow.keras.preprocessing.image import ImageDataGenerator
    HAS_TF = True
except ImportError:
    print("⚠️ TensorFlow not found. Training will be skipped, but data processing can still be tested.")
    HAS_TF = False

from sqlalchemy import create_engine
import cv2

# ==========================================
# CONFIGURATION
# ==========================================
# Set this to FALSE when you are ready to use your real database
USE_MOCK_DATA = False

# Read from env if possible, else default
DB_URL = os.getenv("DATABASE_URL", "postgresql://fil:@localhost/leafcloud")

IMG_SIZE = (224, 224)
BATCH_SIZE = 8
EPOCHS = 20
MODEL_SAVE_PATH = "leafcloud_mobilenetv2_model.h5"

# ==========================================
# 1. DATA LOADING & INTERPOLATION
# ==========================================
def get_dataset():
    """
    Fetches data from Postgres, merges Lab Results, and interpolates missing NPK.
    Returns: A Pandas DataFrame with columns ['image_path', 'n_val', 'p_val', 'k_val']
    """
    if USE_MOCK_DATA:
        print("⚠️ RUNNING IN MOCK MODE: Generating dummy data...")
        return generate_mock_data()

    print("🔌 Connecting to Database...")
    engine = create_engine(DB_URL)

    # A. Fetch Daily Readings (The "Questions")
    # We grab the ID, Date, Image, and the Bottle Label (if it exists)
    query_daily = """
    SELECT id, timestamp, image_path, sample_bottle_label
    FROM daily_readings
    ORDER BY timestamp ASC
    """
    df_daily = pd.read_sql(query_daily, engine)

    # B. Fetch Lab Results (The "Answers")
    query_lab = "SELECT sample_bottle_label, n_val, p_val, k_val FROM lab_results"
    df_lab = pd.read_sql(query_lab, engine)

    # C. Merge Tables
    # This attaches the Lab NPK to the specific days we took samples
    df_merged = pd.merge(df_daily, df_lab, on='sample_bottle_label', how='left')

    # D. Interpolation (The Magic Step)
    # Fills in the blanks between lab tests
    print("ep Calculating missing NPK values via Linear Interpolation...")
    df_merged['n_val'] = df_merged['n_val'].interpolate(method='linear')
    df_merged['p_val'] = df_merged['p_val'].interpolate(method='linear')
    df_merged['k_val'] = df_merged['k_val'].interpolate(method='linear')

    # Drop rows that still have NaN (e.g., days before the first lab test)
    df_final = df_merged.dropna(subset=['n_val', 'p_val', 'k_val', 'image_path'])

    print(f"✅ Data Ready: {len(df_final)} images found for training.")
    return df_final

def generate_mock_data():
    """Generates fake data so you can test the script immediately."""
    # Create 50 fake images
    os.makedirs("mock_images", exist_ok=True)
    mock_data = []
    for i in range(50):
        # Create a black dummy image
        fname = f"mock_images/img_{i}.jpg"
        cv2.imwrite(fname, np.zeros((224, 224, 3), dtype=np.uint8))

        # Fake NPK values that "drift" up and down
        mock_data.append({
            "image_path": fname,
            "n_val": 100 + (i * 2), # Nitrogen rising
            "p_val": 50 + (i * 0.5),
            "k_val": 200 - (i * 1.5)
        })
    return pd.DataFrame(mock_data)

# ==========================================
# 2. DATA GENERATOR (AUGMENTATION)
# ==========================================
def create_generators(df):
    """
    Creates the Keras Data Generator that feeds images to the model.
    Includes Augmentation (Rotation, Flip, etc.)
    """
    if not HAS_TF:
        print("⚠️ TensorFlow missing. Skipping generator creation.")
        return None, None

    # 1. Define Augmentation Rules
    train_datagen = ImageDataGenerator(
        rescale=1./255,         # Normalize pixel values (0-1)
        rotation_range=20,      # Randomly rotate images
        width_shift_range=0.2,  # Shift left/right
        height_shift_range=0.2, # Shift up/down
        horizontal_flip=True,   # Mirror image
        fill_mode='nearest',
        validation_split=0.2    # Use 20% of data for checking accuracy
    )

    # 2. Columns to predict
    y_cols = ['n_val', 'p_val', 'k_val']

    # 3. Create Train Generator
    train_gen = train_datagen.flow_from_dataframe(
        dataframe=df,
        x_col="image_path",
        y_col=y_cols,
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode="raw",       # "raw" because we are predicting numbers, not categories
        subset='training'
    )

    # 4. Create Validation Generator
    val_gen = train_datagen.flow_from_dataframe(
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
    Loads MobileNetV2 and adds a Custom Regression Head.
    """
    if not HAS_TF:
        raise ImportError("Cannot build model without TensorFlow.")

    # Load base model (pre-trained on ImageNet)
    base_model = MobileNetV2(
        weights='imagenet',
        include_top=False,
        input_shape=(IMG_SIZE[0], IMG_SIZE[1], 3)
    )

    # Freeze base layers (optional: unfreeze later for fine-tuning)
    base_model.trainable = False

    # Add custom layers
    x = base_model.output
    x = GlobalAveragePooling2D()(x)
    x = Dense(128, activation='relu')(x)
    x = Dropout(0.2)(x) # Prevents overfitting

    # FINAL OUTPUT LAYER: 3 Neurons (N, P, K) with LINEAR activation
    predictions = Dense(3, activation='linear')(x)

    model = Model(inputs=base_model.input, outputs=predictions)

    # Compile
    model.compile(
        optimizer=Adam(learning_rate=0.001),
        loss='mean_squared_error',  # Standard loss for Regression
        metrics=['mae']             # Mean Absolute Error (easy to understand)
    )

    return model

# ==========================================
# 4. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    # A. Get Data
    df = get_dataset()

    if df.empty:
        print("❌ Error: No data found. Check your database or interpolation.")
    else:
        # B. Prepare Generators
        if HAS_TF:
            train_gen, val_gen = create_generators(df)

            # C. Build Model
            print("🧠 Building MobileNetV2 Model...")
            model = build_model()
            model.summary()

            # D. Train
            print("🚀 Starting Training...")
            history = model.fit(
                train_gen,
                validation_data=val_gen,
                epochs=EPOCHS
            )

            # E. Save
            model.save(MODEL_SAVE_PATH)
            print(f"✅ Model saved to {MODEL_SAVE_PATH}")

            # F. Test Prediction (Optional)
            print("🔍 Running test prediction on one image...")
            test_img, test_label = next(val_gen)
            pred = model.predict(test_img)
            print(f"True Values (N,P,K): {test_label[0]}")
            print(f"Predicted   (N,P,K): {pred[0]}")
        else:
            print("⚠️ Skipping training and model generation due to missing TensorFlow.")
