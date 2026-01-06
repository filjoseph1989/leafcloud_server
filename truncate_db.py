from database import engine
from sqlalchemy import text

def truncate_tables():
    with engine.connect() as connection:
        trans = connection.begin()
        try:
            # Truncate tables with RESTART IDENTITY to reset IDs and CASCADE for FKs
            # We intentionally exclude alembic_version to keep migration history
            print("Truncating tables...")
            connection.execute(text("TRUNCATE TABLE experiments, daily_readings, lab_results, npk_predictions RESTART IDENTITY CASCADE;"))
            trans.commit()
            print("All data truncated successfully.")
        except Exception as e:
            trans.rollback()
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    truncate_tables()
