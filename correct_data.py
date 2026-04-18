import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Expand the path to the environment file
ENV_FILE = os.path.expanduser("~/.env_leafcloud")
load_dotenv(ENV_FILE, override=True)

# Database Connection
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "leafcloud2")
    DATABASE_URL = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def correct_data():
    db = SessionLocal()
    try:
        print("🛠️ Starting Full Data Correction...")
        
        # 1. Update Water Batch IDs
        update_exp_query = text("""
            UPDATE daily_readings 
            SET experiment_id = 4 
            WHERE id >= 947 AND id <= 1043 AND experiment_id != 4
        """)
        db.execute(update_exp_query)

        # 2. Pattern-based pH Correction for ALL Experiments
        corrections = [
            {"id": 1, "ph": 6.94, "name": "NPK"},
            {"id": 2, "ph": 6.91, "name": "Micro"},
            {"id": 3, "ph": 6.91, "name": "Mix"},
            {"id": 4, "ph": 6.72, "name": "Water"}
        ]

        for c in corrections:
            query = text("""
                UPDATE daily_readings 
                SET ph = :ph, 
                    ph_is_estimated = false, 
                    needs_ph_update = false
                WHERE experiment_id = :exp_id AND (ph = 0 OR ph = -1)
            """)
            result = db.execute(query, {"ph": c["ph"], "exp_id": c["id"]})
            print(f"✅ Corrected {result.rowcount} {c['name']} (Exp {c['id']}) records to pH {c['ph']}.")

        # 3. Time Shift: Move all data 2 hours BEFORE
        # This moves 2026-04-15 00:XX back to 2026-04-14 22:XX
        print("🕒 Shifting timestamps back by 2 hours...")
        
        # Shift Daily Readings
        time_shift_readings = text("""
            UPDATE daily_readings 
            SET timestamp = timestamp - INTERVAL '2 hours'
        """)
        db.execute(time_shift_readings)
        
        # Shift NPK Predictions to match
        time_shift_predictions = text("""
            UPDATE npk_predictions 
            SET prediction_date = prediction_date - INTERVAL '2 hours'
        """)
        db.execute(time_shift_predictions)
        
        print("✅ All timestamps shifted back by 2 hours.")

        db.commit()
        print("🚀 All data patterns corrected and timestamps shifted.")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error during correction: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    correct_data()
