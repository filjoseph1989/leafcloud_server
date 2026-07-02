import logging
import tensorflow as tf
import builtins
builtins.tf = tf
tf.keras.layers.Lambda.compute_output_shape = lambda self, input_shape: input_shape
import numpy as np
import cv2
import os
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import DailyReading, ImageCrop, NPKPrediction
from app.services.image_processing import calculate_greenness, get_crop_coordinates
import uuid
import shutil

logger = logging.getLogger(__name__)

@tf.keras.utils.register_keras_serializable(package="Custom")
class StopGradient(tf.keras.layers.Layer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def call(self, inputs):
        return tf.stop_gradient(inputs)

    def compute_output_shape(self, input_shape):
        return input_shape

# Global variable to cache the loaded model
_MODEL = None

def get_model():
    """Loads and caches the AI model."""
    global _MODEL
    if _MODEL is None:
        if os.path.exists(settings.AI_MODEL_PATH):
            logger.info(f"Loading AI Model from {settings.AI_MODEL_PATH}...")
            _MODEL = tf.keras.models.load_model(
                settings.AI_MODEL_PATH, 
                safe_mode=False, 
                custom_objects={'StopGradient': StopGradient}
            )
        else:
            logger.error(f"AI Model file not found at {settings.AI_MODEL_PATH}")
    return _MODEL

def process_iot_data_background(cleaned_reading_id: int):
    """
    Background task to process the uploaded image and perform AI prediction.
    Separated into a standalone function for BackgroundTasks.
    """
    db = SessionLocal()
    try:
        # 1. Fetch the reading
        reading = db.query(DailyReading).filter(DailyReading.id == cleaned_reading_id).first()
        if not reading:
            logger.error(f"Background task failed: Reading {cleaned_reading_id} not found")
            return

        # 2. Start Cropping Logic
        logger.info(f"Processing crops for reading {reading.id}...")
        img = cv2.imread(reading.image_path)
        if img is None:
            logger.error(f"Could not read image for cropping: {reading.image_path}")
            return

        h, w = img.shape[:2]
        coords = get_crop_coordinates(w, h, settings.CROP_SIZE)
        
        valid_crops = []
        base_name = os.path.splitext(os.path.basename(reading.image_path))[0]
        dest_folder = os.path.dirname(reading.image_path) # Save in same folder as raw

        for x, y, crop_type in coords:
            crop_img = img[y:y+settings.CROP_SIZE, x:x+settings.CROP_SIZE]
            unique_id = uuid.uuid4().hex[:4]
            temp_path = f"temp_{unique_id}.jpg"
            cv2.imwrite(temp_path, crop_img)
            
            if calculate_greenness(temp_path) >= settings.GREEN_THRESHOLD:
                final_name = f"crop_{base_name}_{crop_type}_{y}_{x}_{unique_id}.jpg"
                final_path = os.path.join(dest_folder, final_name)
                shutil.move(temp_path, final_path)
                
                # NOTE: Gi-comment out ang pag-save sa DB kay i-delete ra nato ang file taod-taod
                # para dili mapuno ang server, ug para walay broken image links sa DB.
                # new_crop = ImageCrop(
                #     daily_reading_id=reading.id,
                #     crop_path=final_path.replace("\\", "/"),
                #     crop_type=crop_type
                # )
                # db.add(new_crop)
                valid_crops.append((crop_img, final_path))
            else:
                os.remove(temp_path)

        db.commit()
        logger.info(f"Generated {len(valid_crops)} valid crops for reading {reading.id}")

        # 3. AI Prediction
        model = get_model()
        if model and valid_crops:
            logger.info(f"Running AI Prediction for reading {reading.id}...")
            
            # Prepare inputs
            # The model expects [images, sensors]
            # Normalize sensors — must match nutrient_classifier_v5.py SENSOR_NORM exactly.
            # ec range changed from (0.0, 3.0) to (0.0, 1.6) in V5: actual data spans 0.04–1.51.
            ph_norm = (np.clip(reading.ph, 3.0, 10.0) - 3.0) / (10.0 - 3.0)
            ec_norm = (np.clip(reading.ec, 0.0, 1.6) - 0.0) / (1.6 - 0.0)
            temp_norm = (np.clip(reading.water_temp, 24.0, 29.0) - 24.0) / (29.0 - 24.0)
            
            sensor_input = np.array([[ph_norm, ec_norm, temp_norm]], dtype=np.float32)
            
            # Use the first 5 valid crops for an ensemble average prediction
            all_clf_preds = []
            all_reg_preds = []
            for crop_img, _ in valid_crops[:5]:
                # Resize and preprocess image
                resized = cv2.resize(crop_img, (224, 224))
                # preprocess_input: scale to -1 to 1
                img_input = (resized.astype(np.float32) / 127.5) - 1.0
                img_input = np.expand_dims(img_input, axis=0)
                
                # Model returns [clf_output, reg_output]
                clf_pred, reg_pred = model.predict([img_input, sensor_input], verbose=0)
                all_clf_preds.append(clf_pred[0])
                all_reg_preds.append(reg_pred[0])
            
            # Average the predictions
            avg_clf = np.mean(all_clf_preds, axis=0) # [prob_water, prob_npk, prob_micro, prob_mix]
            avg_reg = np.mean(all_reg_preds, axis=0) # [macro_scale, micro_scale]
            
            # Classification Output (Label Mapping from training script)
            LABEL_LIST = ['Water', 'NPK', 'Micro', 'Mix']
            class_idx = np.argmax(avg_clf)
            predicted_class = LABEL_LIST[class_idx]
            confidence = float(avg_clf[class_idx])
            
            # Regression Output — sigmoid output is already [0, 1]; clip guards against float edge cases
            macro_scale = float(np.clip(avg_reg[0], 0.0, 1.0))
            micro_scale = float(np.clip(avg_reg[1], 0.0, 1.0))
            
            # Sanity Check (Anomaly Detection)
            is_anomaly = False
            if predicted_class == 'Water' and (macro_scale > 0.5 or micro_scale > 0.5):
                logger.warning(f"Anomaly Detected! AI sees 'Water' but regression predicted high nutrients (Macro: {macro_scale:.2f}, Micro: {micro_scale:.2f})")
                is_anomaly = True
            elif predicted_class == 'NPK' and micro_scale > 0.5:
                logger.warning(f"Anomaly Detected! AI sees 'NPK' (Macro) but regression predicted high Micro ({micro_scale:.2f})")
                is_anomaly = True
            elif predicted_class == 'Micro' and macro_scale > 0.5:
                logger.warning(f"Anomaly Detected! AI sees 'Micro' but regression predicted high Macro ({macro_scale:.2f})")
                is_anomaly = True
            
            prediction_record = NPKPrediction(
                daily_reading_id=reading.id,
                predicted_class=predicted_class,
                is_anomaly=is_anomaly,
                macro_scale=macro_scale,
                micro_scale=micro_scale,
                # Legacy columns — no longer used by the new model, set to 0 to avoid breaking the DB schema
                predicted_n=0.0,
                predicted_p=0.0,
                predicted_k=0.0,
                confidence_score=confidence
            )
            db.add(prediction_record)
            db.commit()
            logger.info(f"AI Prediction complete for reading {reading.id}")

        # --- CLEANUP STRATEGY: Delete cropped images to save server disk space ---
        logger.info(f"Cleaning up {len(valid_crops)} crop images from server...")
        for _, crop_file_path in valid_crops:
            if os.path.exists(crop_file_path):
                os.remove(crop_file_path)
        # --------------------------------------------------------------------------

    except Exception as e:
        logger.error(f"Background processing error: {e}")
    finally:
        db.close()
