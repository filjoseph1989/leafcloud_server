import os
import re
import shutil
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")

ENV_FILE = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_FILE, override=True)

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

# Matches: reading_<TYPE>_<YYYYMMDD>_<HHMMSS>.jpg
FILENAME_RE = re.compile(r"^reading_([^_]+)_(\d{4})(\d{2})(\d{2})_\d+\.jpg$")


def derive_new_path(filename: str) -> str | None:
    """Return new relative path like images/2026-03-08/NPK/reading_NPK_....jpg"""
    m = FILENAME_RE.match(filename)
    if not m:
        return None
    sensor_type, year, month, day = m.group(1), m.group(2), m.group(3), m.group(4)
    return f"images/{year}-{month}-{day}/{sensor_type}/{filename}"


def organize_images():
    db = SessionLocal()
    try:
        print("Starting image organization and DB update...")

        rows = db.execute(text(
            "SELECT id, image_path FROM daily_readings WHERE image_path IS NOT NULL"
        )).fetchall()
        print(f"Found {len(rows)} DB rows with image_path.")

        moved = 0
        already_done = 0
        missing = 0
        errors = 0

        for row_id, old_rel_path in rows:
            filename = os.path.basename(old_rel_path)
            new_rel_path = derive_new_path(filename)

            if new_rel_path is None:
                print(f"  SKIP (filename pattern mismatch): {filename}")
                continue

            if old_rel_path == new_rel_path:
                already_done += 1
                continue

            src_abs = os.path.join(BASE_DIR, old_rel_path)
            dest_abs = os.path.join(BASE_DIR, new_rel_path)

            # Move file if it exists at source and not yet at destination
            if os.path.exists(src_abs):
                os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
                shutil.move(src_abs, dest_abs)
                moved += 1
            elif os.path.exists(dest_abs):
                # File already moved but DB not updated yet
                pass
            else:
                print(f"  MISSING: {old_rel_path}")
                missing += 1
                continue

            # Update DB path
            try:
                db.execute(
                    text("UPDATE daily_readings SET image_path = :new WHERE id = :id"),
                    {"new": new_rel_path, "id": row_id},
                )
            except Exception as e:
                print(f"  DB error for id={row_id}: {e}")
                errors += 1

        db.commit()
        print(f"\nDone.")
        print(f"  Files moved:         {moved}")
        print(f"  Already organized:   {already_done}")
        print(f"  Missing files:       {missing}")
        print(f"  DB errors:           {errors}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    organize_images()
