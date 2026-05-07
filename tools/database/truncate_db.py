import os
import shutil
from sqlalchemy import text
from database import engine
from models import Base

def truncate_tables():
  """
  Resets the database by truncating all application tables and clearing storage.
  """
  # 1. Truncate Database Tables
  # We use Base.metadata.tables.keys() to dynamically get all tables from our models.
  # This ensures that if new tables are added to models.py, they are also truncated here.
  # alembic_version is NOT in Base.metadata, so it will be preserved.
  tables = list(Base.metadata.tables.keys())

  if not tables:
    print("No tables found in models.")
    return

  print(f"🔄 Truncating tables: {', '.join(tables)}...")

  with engine.begin() as connection:
    try:
      # PostgreSQL TRUNCATE command with:
      # RESTART IDENTITY: Resets the auto-incrementing IDs to 1.
      # CASCADE: Automatically truncates tables that have foreign keys to these tables.
      truncate_query = f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE;"
      connection.execute(text(truncate_query))
      print("✅ All database tables truncated and IDs reset.")
    except Exception as e:
      print(f"❌ Database error: {e}")
      return

  # 2. Clear Image Storage
  # The application stores physical images in 'images/' (and 'mock_images/' during training).
  # A full reset should also clear these files to prevent "ghost" data.
  storage_dirs = ["images", "mock_images"]
  for directory in storage_dirs:
    if os.path.exists(directory):
      print(f"🧹 Clearing {directory}/ directory...")
      try:
        # We delete the contents but keep the directory itself
        for filename in os.listdir(directory):
          file_path = os.path.join(directory, filename)
          if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
          elif os.path.isdir(file_path):
            shutil.rmtree(file_path)
        print(f"✅ {directory}/ cleared.")
      except Exception as e:
        print(f"⚠️ Could not fully clear {directory}/: {e}")

if __name__ == "__main__":
  # Add a safety confirmation prompt
  confirm = input("⚠️  WARNING: This will DELETE ALL DATA and CLEAR ALL IMAGES. Proceed? (y/N): ")
  if confirm.lower() == 'y':
    truncate_tables()
    print("🚀 System reset complete.")
  else:
    print("Aborted.")
