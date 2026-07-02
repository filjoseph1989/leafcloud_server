import sys
import os
import argparse
import json

# Auto-resolve parent directory to allow running the script directly from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models import DailyReading, NPKPrediction
from app.models.tank_config import TankConfig
from app.services.alert_service import get_tank_alert_status

def test_alert(tank_id: int, macro_scale: float, micro_scale: float):
    db = SessionLocal()
    try:
        # 1. Fetch Tank Config
        tank = db.query(TankConfig).filter(TankConfig.id == tank_id).first()
        if not tank:
            print(f"❌ Error: Tank with ID {tank_id} not found in database.")
            return

        # 2. Get the latest reading for this tank
        latest_reading = (
            db.query(DailyReading)
            .filter(DailyReading.tank_id == tank_id)
            .order_by(DailyReading.timestamp.desc())
            .first()
        )
        if not latest_reading:
            print(f"❌ Error: No readings found for Tank '{tank.tank_name}'. Please run scripts/seed_predictions.py first.")
            return

        # 3. Find or Create the NPKPrediction row
        prediction = (
            db.query(NPKPrediction)
            .filter(NPKPrediction.daily_reading_id == latest_reading.id)
            .first()
        )
        if not prediction:
            prediction = NPKPrediction(daily_reading_id=latest_reading.id)
            db.add(prediction)

        # 4. Set custom mock scales
        prediction.macro_scale = macro_scale
        prediction.micro_scale = micro_scale
        prediction.predicted_class = "Mix"
        prediction.is_anomaly = False
        db.commit()
        db.refresh(prediction)

        print(f"✅ Set latest reading (ID: {latest_reading.id}) to custom scales:")
        print(f"   - Macro Scale: {macro_scale} (Target: {tank.target_macro_dosage_mll} mL/L in {tank.water_volume_liters}L)")
        print(f"   - Micro Scale: {micro_scale} (Target: {tank.target_micro_dosage_mll} mL/L in {tank.water_volume_liters}L)")
        print("-" * 50)

        # 5. Evaluate alert status
        alert_status = get_tank_alert_status(db, tank)
        
        # Format output
        alert_dict = {
            "tank_id": alert_status.tank_id,
            "tank_name": alert_status.tank_name,
            "has_alert": alert_status.has_alert,
            "level": alert_status.level,
            "message": alert_status.message,
            "topup_macro_ml": alert_status.topup_macro_ml,
            "topup_micro_ml": alert_status.topup_micro_ml,
            "last_reading_at": alert_status.last_reading_at.isoformat() if alert_status.last_reading_at else None
        }
        
        print("📣 Simulated API Alert Status Response:")
        print(json.dumps(alert_dict, indent=2))
        
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test and trigger nutrient alerts manually by seting mock scales.")
    parser.add_argument("--tank-id", type=int, default=1, help="ID of the tank to test (default: 1)")
    parser.add_argument("--macro", type=float, default=0.6, help="Mock macro scale ratio, e.g. 0.6 = 60%% (default: 0.6)")
    parser.add_argument("--micro", type=float, default=0.8, help="Mock micro scale ratio, e.g. 0.8 = 80%% (default: 0.8)")
    
    args = parser.parse_args()
    test_alert(args.tank_id, args.macro, args.micro)
