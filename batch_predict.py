import os
import numpy as np
import tensorflow as tf
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from PIL import Image
from tqdm import tqdm

# Load Model
MODEL_PATH = "leafcloud_regression_model.keras"
try:
    model = tf.keras.models.load_model(MODEL_PATH)
    print("🧠 AI Model loaded successfully.")
except Exception as e:
    print(f"❌ Error loading model: {e}")
    exit(1)

def batch_predict():
    db = SessionLocal()
    try:
        # Find DailyReadings that don't have predictions yet
        readings = db.query(models.DailyReading).filter(
            ~models.DailyReading.prediction.has()
        ).all()
        
        print(f"Processing {len(readings)} readings lacking predictions...")
        
        for reading in tqdm(readings):
            # Check if we have crops for this reading
            crops = db.query(models.ImageCrop).filter(models.ImageCrop.daily_reading_id == reading.id).all()
            
            if not crops:
                continue
                
            # Aggregate predictions from all crops
            crop_preds = []
            for crop in crops:
                if not os.path.exists(crop.crop_path):
                    continue
                
                try:
                    img = Image.open(crop.crop_path).convert('RGB').resize((224, 224))
                    img_array = np.expand_dims(np.array(img) / 255.0, axis=0)
                    prediction = model.predict(img_array, verbose=0)
                    crop_preds.append(prediction[0])
                except Exception as e:
                    print(f"Error predicting crop {crop.id}: {e}")

            if crop_preds:
                # Average the predictions from all crops
                avg_pred = np.mean(crop_preds, axis=0)
                npk_ml_l, micro_ml_l = avg_pred
                
                # Precise Mapping (8-15-15 and 8-15-36)
                predicted_n = max(0.0, (npk_ml_l * 80.0) + (micro_ml_l * 80.0))
                predicted_p = max(0.0, (npk_ml_l * 150.0) + (micro_ml_l * 150.0))
                predicted_k = max(0.0, (npk_ml_l * 150.0) + (micro_ml_l * 360.0))

                # Update or Create Prediction
                pred_record = db.query(models.NPKPrediction).filter(models.NPKPrediction.daily_reading_id == reading.id).first()
                if not pred_record:
                    pred_record = models.NPKPrediction(daily_reading_id=reading.id)
                    db.add(pred_record)
                
                pred_record.predicted_n = float(predicted_n)
                pred_record.predicted_p = float(predicted_p)
                pred_record.predicted_k = float(predicted_k)
                pred_record.prediction_date = reading.timestamp # Sync dates
                
        db.commit()
        print("\n✅ Batch Prediction Complete.")
        
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    batch_predict()
