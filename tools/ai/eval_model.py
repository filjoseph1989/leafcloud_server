import os
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import load_model

# CONFIGURATION
MODEL_PATH = "leafcloud_regression_model.keras"
LOCAL_DATA_DIR = "/Users/fil/.gemini/tmp/leafcloud_training_data"
IMG_SIZE = (224, 224)

# Load Model
print(f"Loading model from {MODEL_PATH}...")
model = load_model(MODEL_PATH)

# Test on 5 samples from different buckets if possible
# We can extract the bucket from the filename if we had kept it, 
# but our copy logic used unique names.
# Let's just pick 10 random files from the local dir.

files = [f for f in os.listdir(LOCAL_DATA_DIR) if f.endswith(".jpg")]
samples = np.random.choice(files, 10)

print("\n--- Model Predictions (NPK, Micro) ---")
for f in samples:
    img_path = os.path.join(LOCAL_DATA_DIR, f)
    img = tf.keras.utils.load_img(img_path, target_size=IMG_SIZE)
    img_array = tf.keras.utils.img_to_array(img) / 255.0
    img_array = np.expand_dims(img_array, axis=0)
    
    pred = model.predict(img_array, verbose=0)
    print(f"File: {f}")
    print(f"Predicted: NPK: {pred[0][0]:.2f} ml/L, Micro: {pred[0][1]:.2f} ml/L")
    print("-" * 30)
