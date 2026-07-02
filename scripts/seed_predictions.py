
# [STEP 1] Add the project root folder to Python's module search path so imports like
# "from app.core..." work even when running this script directly from the terminal.
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [STEP 2] Import standard Python libraries needed throughout this script.
import random       # for picking a random image and generating random sensor values
import logging      # for printing info/error messages to the terminal
import shutil       # for copying image files
import uuid         # for generating unique filenames so files never overwrite each other
from datetime import datetime, timedelta  # for getting the current date/time
from pathlib import Path                  # for building file/folder paths cleanly

# [STEP 3] Import project-specific modules: database session, app settings, DB models,
# and the AI service function that runs the model.
from app.core.database import SessionLocal
from app.core.config import settings
from app.models import DailyReading, NPKPrediction
from app.models.tank_config import TankConfig
from app.services.ai_service import process_iot_data_background

# [STEP 4] Set up logging so all logger.info() and logger.error() calls print to the terminal.
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


# Python reads and registers this function definition, but does NOT run its body yet.
def seed_daily_readings(count: int = 50):
    """
    Simulates Raspberry Pi uploads by copying random images from images/captures/
    and creating daily_readings rows with randomized sensor values.
    """
    # [STEP 7] Open a database session so we can read/write to the DB.
    db = SessionLocal()
    try:
        # [STEP 8] Build the path to the folder that holds the sample/stock images
        # (e.g. images/captures/). These are the pool of images we randomly pick from.
        source_dir = Path(settings.SOURCE_DIR) / "captures"

        # [STEP 9] Get a list of all .jpg files inside that captures folder.
        all_images = list(source_dir.glob("*.jpg"))

        # [STEP 10] If there are no images in that folder, log an error and stop — nothing to seed.
        if not all_images:
            logger.error(f"No source images found in {source_dir}")
            return

        # [STEP 11] Query the DB for the tank with ID=1. We assign all fake readings to this tank.
        tank = db.query(TankConfig).filter(TankConfig.id == 1).first()

        # [STEP 12] If tank ID=1 doesn't exist in the DB, log an error and stop.
        if not tank:
            logger.error("No tanks found in DB")
            return

        logger.info(f"Seeding {count} daily readings...")

        # [STEP 13] Start a counter to track how many readings we successfully create.
        created = 0

        # [STEP 14] Loop `count` times (here count=1, set at STEP 6).
        # Each iteration creates one fake sensor reading + one copied image.
        for _ in range(count):

            # [STEP 15] Pick a random image from the captures folder to use as the fake upload.
            source_image = random.choice(all_images)

            # [STEP 16] Get the current date and time in two formats:
            # date_str      → "2026-05-30"        (used for the folder name)
            # timestamp_str → "20260530_123045"   (used in the image filename)
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            timestamp_str = now.strftime("%Y%m%d_%H%M%S")

            # [STEP 17] Build the destination folder path where this fake image will be saved.
            # Format: images/2026-05-30/Tank_1/
            # Spaces in the tank name are replaced with underscores for safe folder names.
            folder_path = Path(settings.SOURCE_DIR) / date_str / tank.tank_name.replace(" ", "_")

            # [STEP 18] Create the folder if it doesn't exist yet (parents=True creates all
            # intermediate folders too; exist_ok=True skips the error if it already exists).
            folder_path.mkdir(parents=True, exist_ok=True)

            # [STEP 19] Build a unique filename using the timestamp + a short random hex suffix
            # so two readings created in the same second don't collide.
            # Example: reading_20260530_123045_a3f9c2.jpg
            filename = f"reading_{timestamp_str}_{uuid.uuid4().hex[:6]}.jpg"
            dest_path = folder_path / filename

            # [STEP 20] Copy the randomly chosen stock image to the destination path.
            # shutil.copy2 also preserves file metadata (timestamps, etc.).
            shutil.copy2(source_image, dest_path)

            # [STEP 21] Create a DailyReading DB object with:
            # - the path to the copied image
            # - randomized sensor values (ph, ec, water_temp) in realistic ranges
            # - is_new_data=True and status="pending" to mark it as unprocessed
            reading = DailyReading(
                timestamp=now,
                image_path=str(dest_path).replace("\\", "/"),  # normalize Windows backslashes
                ph=round(random.uniform(5.5, 7.0), 2),
                ec=round(random.uniform(0.04, 1.51), 2),  # matches actual training data range (0.04–1.51 mS/cm)
                water_temp=round(random.uniform(24.0, 29.0), 1),
                tank_id=tank.id,
                is_new_data=True
            )

            # [STEP 22] Stage the new reading object so it will be saved on the next db.commit().
            db.add(reading)

            # [STEP 23] Increment the counter so we can report how many were created.
            created += 1

        # [STEP 24] Write all staged readings to the database in one transaction.
        db.commit()
        logger.info(f"✅ Created {created} daily readings.")

    except Exception as e:
        # [STEP 24 - ERROR PATH] If anything went wrong, log the error and undo all DB changes
        # made in this session so the DB is not left in a half-written state.
        logger.error(f"Error seeding daily readings: {e}")
        db.rollback()
    finally:
        # [STEP 25] Always close the DB session whether it succeeded or failed.
        db.close()


# Python reads and registers this function definition, but does NOT run its body yet.
def seed_predictions():
    """
    Runs the real AI model on the latest daily_reading that doesn't have a prediction yet.
    """
    # [STEP 28] Open a new DB session to query for an unprocessed reading.
    db = SessionLocal()
    try:
        # [STEP 29] Query for the most recent DailyReading that has NO linked NPKPrediction yet.
        # outerjoin includes readings even if there is no matching NPKPrediction row.
        # filter(NPKPrediction.id == None) keeps only those with no prediction.
        # order_by(...desc()).first() picks the newest one.
        reading = db.query(DailyReading).outerjoin(NPKPrediction).filter(
            NPKPrediction.id == None
        ).order_by(DailyReading.timestamp.desc()).first()

        # [STEP 30] If every reading already has a prediction, nothing to do — log and exit.
        if not reading:
            logger.info("No readings found that need predictions.")
            return

        logger.info(f"Running AI prediction for reading ID {reading.id}...")

    finally:
        # [STEP 31] Close the DB session BEFORE running the AI model.
        # The AI service (process_iot_data_background) opens its own separate DB session,
        # so we close this one first to avoid holding a transaction open during slow inference.
        db.close()

    # [STEP 32] Run the full AI pipeline for this reading:
    # crops the image → filters by greenness → runs the TensorFlow model →
    # averages predictions across up to 5 crops → saves the NPKPrediction row → deletes crop files.
    process_iot_data_background(reading.id)
    logger.info("✅ AI prediction complete.")


# [STEP 5] Python has finished reading the whole file. Now it hits this block and starts
# actual execution. This is the real entry point when you run:
#   python scripts/seed_predictions.py
if __name__ == "__main__":
    # [STEP 6] Call seed_daily_readings with count=1 — jumps up into that function body now.
    seed_daily_readings(count=1)

    # [STEP 27] seed_daily_readings() is done. Now call seed_predictions() — jumps into that function body.
    seed_predictions()
