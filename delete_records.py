import os
import re
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

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

RESULT_FILE = os.path.join(BASE_DIR, "database-query.result")

def parse_result_file(file_path):
    records = []
    # Matches lines like:  2757 | 2026-04-18 ... | images/2026-04-18/NPK/reading_NPK_20260418_202649.jpg | ...
    # We only care about the first and third column
    with open(file_path, 'r') as f:
        for line in f:
            if "|" not in line or "id" in line or "---" in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                try:
                    record_id = int(parts[0])
                    image_path = parts[2]
                    records.append((record_id, image_path))
                except ValueError:
                    continue
    return records

def delete_records():
    if not os.path.exists(RESULT_FILE):
        print(f"❌ Result file not found: {RESULT_FILE}")
        return

    records = parse_result_file(RESULT_FILE)
    if not records:
        print("⚠️ No records found to delete.")
        return

    print(f"🔄 Starting deletion of {len(records)} records...")
    
    db = SessionLocal()
    files_deleted = 0
    records_deleted = 0
    errors = 0

    try:
        for record_id, image_path in records:
            # 1. Delete physical file
            abs_path = os.path.join(BASE_DIR, image_path)
            if os.path.exists(abs_path):
                try:
                    os.remove(abs_path)
                    files_deleted += 1
                except Exception as e:
                    print(f"  ⚠️ Failed to delete file {image_path}: {e}")
            
            # 2. Delete from DB (NPKPrediction first then DailyReading)
            try:
                # Delete related NPK predictions
                db.execute(text("DELETE FROM npk_predictions WHERE daily_reading_id = :id"), {"id": record_id})
                # Delete the reading itself
                db.execute(text("DELETE FROM daily_readings WHERE id = :id"), {"id": record_id})
                records_deleted += 1
            except Exception as e:
                print(f"  ❌ DB Error for ID {record_id}: {e}")
                errors += 1

        db.commit()
        print(f"\n✅ Deletion complete.")
        print(f"  Files deleted:   {files_deleted}")
        print(f"  Records deleted: {records_deleted}")
        print(f"  Errors:          {errors}")

    except Exception as e:
        db.rollback()
        print(f"💥 Fatal Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    delete_records()
