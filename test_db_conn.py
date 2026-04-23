from database import engine, SessionLocal
from sqlalchemy import text

def test_connection():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT current_database()")).fetchone()
            print(f"Connected to database: {result[0]}")
            if result[0] == "leafcloud2":
                print("✅ Correct database connected.")
            else:
                print(f"❌ Connected to {result[0]} instead of leafcloud2.")
    except Exception as e:
        print(f"❌ Connection error: {e}")

if __name__ == "__main__":
    test_connection()
