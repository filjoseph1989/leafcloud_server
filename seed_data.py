import random
import os
import cv2
import numpy as np
from datetime import datetime, timedelta
from database import SessionLocal, engine, Base
from models import Experiment, DailyReading, LabResult, NPKPrediction

# Ensure tables exist (redundant if migrations ran, but good for safety)
Base.metadata.create_all(bind=engine)

def seed():
    db = SessionLocal()
    
    # Ensure images directory exists
    os.makedirs("images", exist_ok=True)
    
    # The 7 Experimental Conditions (Buckets) from Protocol
    buckets = [
        {"label": "BucketA-Balanced", "n_mult": 1.0, "p_mult": 1.0, "k_mult": 1.0},
        {"label": "BucketB-LowN",    "n_mult": 0.15, "p_mult": 1.0, "k_mult": 1.0},
        {"label": "BucketC-HighN",   "n_mult": 2.0,  "p_mult": 1.0, "k_mult": 1.0},
        {"label": "BucketD-LowK",    "n_mult": 1.0,  "p_mult": 1.0, "k_mult": 0.15},
        {"label": "BucketE-HighK",   "n_mult": 1.0,  "p_mult": 1.0, "k_mult": 2.5},
        {"label": "BucketF-LowP",    "n_mult": 1.0,  "p_mult": 0.1, "k_mult": 1.0},
        {"label": "BucketG-HighP",   "n_mult": 1.0,  "p_mult": 2.0, "k_mult": 1.0},
    ]

    # Standard "Healthy" Lettuce Targets (ppm)
    BASE_N = 150.0
    BASE_P = 50.0
    BASE_K = 200.0

    # Simulation Start Date
    start_date = datetime.now().date() - timedelta(days=20)

    print("🌱 Seeding database with experimental data (V2 Schema)...")
    print("🖼️  Generating dummy images in 'images/' folder...")

    for bucket in buckets:
        print(f"   Processing {bucket['label']}...")
        
        # 1. Create Experiment Batch
        experiment = Experiment(
            bucket_label=bucket['label'],
            start_date=start_date
        )
        db.add(experiment)
        db.commit()
        db.refresh(experiment)

        # 2. Simulate 20 days of growth
        for day in range(1, 21):
            current_date = datetime.combine(start_date + timedelta(days=day), datetime.min.time())
            
            # --- Determine if this is a Lab Day ---
            is_lab_day = day in [5, 10, 15]
            sample_label = f"{bucket['label']}-Day{day}" if is_lab_day else None

            # --- Calculate Current NPK (Drift) ---
            # Add some random noise (+/- 5%) to make it realistic
            n_actual = (BASE_N * bucket['n_mult']) * random.uniform(0.95, 1.05)
            p_actual = (BASE_P * bucket['p_mult']) * random.uniform(0.95, 1.05)
            k_actual = (BASE_K * bucket['k_mult']) * random.uniform(0.95, 1.05)

            # --- Create Lab Result (Ground Truth) if applicable ---
            if is_lab_day:
                lab_result = LabResult(
                    sample_bottle_label=sample_label,
                    n_val=round(n_actual, 2),
                    p_val=round(p_actual, 2),
                    k_val=round(k_actual, 2)
                )
                db.add(lab_result)

            # --- Create Daily Reading (Sensor + Image) ---
            # Simulate slight drift based on nutrient concentration
            base_ec = 1.2
            ec_val = base_ec * ((bucket['n_mult'] + bucket['p_mult'] + bucket['k_mult']) / 3)
            ec_val = ec_val * random.uniform(0.9, 1.1) # Noise
            
            image_filename = f"sim_{bucket['label']}_day{day:02d}.jpg"
            full_image_path = os.path.join("images", image_filename)
            
            # Generate Physical Dummy Image (Green square with random noise)
            # 224x224 is standard for MobileNet
            dummy_img = np.zeros((224, 224, 3), dtype=np.uint8)
            # Set background to green-ish
            dummy_img[:] = (34, 139, 34) 
            # Add some noise to make file size realistic
            noise = np.random.randint(0, 50, (224, 224, 3), dtype=np.uint8)
            dummy_img = cv2.add(dummy_img, noise)
            
            cv2.imwrite(full_image_path, dummy_img)
            
            reading = DailyReading(
                bucket_id=experiment.id,
                timestamp=current_date,
                image_path=f"images/{image_filename}", # Relative path
                ph=round(random.uniform(5.8, 6.2), 2),
                ec=round(ec_val, 2),
                water_temp=round(random.uniform(22.0, 26.0), 1),
                sample_bottle_label=sample_label
            )
            db.add(reading)
            db.commit() # Commit reading to get ID

            # --- Create NPK Prediction (AI Output) ---
            # Simulate AI being somewhat accurate but not perfect
            accuracy_factor = 0.85 if day < 7 else 0.95 

            pred_n = n_actual * random.uniform(accuracy_factor, 2 - accuracy_factor)
            pred_p = p_actual * random.uniform(accuracy_factor, 2 - accuracy_factor)
            pred_k = k_actual * random.uniform(accuracy_factor, 2 - accuracy_factor)

            prediction = NPKPrediction(
                daily_reading_id=reading.id,
                predicted_n=round(pred_n, 2),
                predicted_p=round(pred_p, 2),
                predicted_k=round(pred_k, 2),
                confidence_score=round(random.uniform(0.70, 0.99), 2),
                prediction_date=current_date
            )
            db.add(prediction)

    db.commit()
    db.close()
    print("✅ Seeding complete! Added data and generated 140 dummy images.")

if __name__ == "__main__":
    seed()