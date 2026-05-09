"""
Seeder for testing all dashboard classification states on the mobile app.
Inserts one DailyReading + NPKPrediction per classification case so the
mobile app can cycle through each banner state without waiting for the CNN.

Usage:
    # Seed all 5 states (latest = under_dosed)
    ~/.env_leafcloud_3.11/bin/python tools/database/seed_dashboard_states.py

    # Seed all 5 states with random values and a shuffled order (latest will vary)
    ~/.env_leafcloud_3.11/bin/python tools/database/seed_dashboard_states.py --random --shuffle

    # Seed 5 random variations of the 'optimal' state
    ~/.env_leafcloud_3.11/bin/python tools/database/seed_dashboard_states.py --state optimal --random --count 5

    # Seed one single random state (good for quick dashboard refresh)
    ~/.env_leafcloud_3.11/bin/python tools/database/seed_dashboard_states.py --clean --random-state --random

    # Cleanup lang
    ~/.env_leafcloud_3.11/bin/python tools/database/seed_dashboard_states.py --clean

Options:
    --state <name>    Seed only one specific state
    --random-state    Seed one randomly chosen state
    --clean           Remove all seeded records before inserting
    --random          Randomize values within state-specific ranges (pH, EC, NPK)
    --count <n>       Number of records to seed per state (default: 1)
    --shuffle         Shuffle the order of states (affects which one is 'latest')

States:
    optimal | macro_deficiency | ph_lockout | over_dosed | under_dosed
"""

import sys
import os
import argparse
import random
from datetime import datetime, timedelta
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from database import SessionLocal
import models

EXPERIMENT_ID = "SEED-DASHBOARD-TEST"
SEED_TAG = "[seeded]"

# Baseline values for each state
STATES = {
    "optimal": {
        "label": "Optimal",
        "ph": 6.2,
        "ec": 1.8,
        "temp": 25.0,
        "n": 200.0,
        "p": 350.0,
        "k": 600.0,
        "color": (34, 139, 34), # ForestGreen
    },
    "macro_deficiency": {
        "label": "Macro-Deficiency",
        "ph": 6.0,
        "ec": 1.2,
        "temp": 24.5,
        "n": 80.0,
        "p": 180.0,
        "k": 300.0,
        "color": (218, 165, 32), # GoldenRod
    },
    "ph_lockout": {
        "label": "pH Lockout",
        "ph": 7.8,
        "ec": 1.5,
        "temp": 25.0,
        "n": 200.0,
        "p": 350.0,
        "k": 600.0,
        "color": (255, 69, 0), # OrangeRed
    },
    "over_dosed": {
        "label": "Over-Dosed",
        "ph": 6.1,
        "ec": 3.2,
        "temp": 26.0,
        "n": 300.0,
        "p": 500.0,
        "k": 800.0,
        "color": (178, 34, 34), # FireBrick
    },
    "under_dosed": {
        "label": "Under-Dosed",
        "ph": 6.3,
        "ec": 0.3,
        "temp": 25.5,
        "n": 50.0,
        "p": 80.0,
        "k": 120.0,
        "color": (70, 130, 180), # SteelBlue
    },
}

# Ranges for randomization
STATE_RANGES = {
    "optimal": {
        "ph": (5.8, 6.4),
        "ec": (1.6, 2.2),
        "temp": (23.0, 27.0),
        "n": (180.0, 220.0),
        "p": (330.0, 370.0),
        "k": (550.0, 650.0),
    },
    "macro_deficiency": {
        "ph": (5.5, 6.5),
        "ec": (1.0, 1.4),
        "temp": (23.0, 27.0),
        "n": (60.0, 100.0),
        "p": (150.0, 210.0),
        "k": (250.0, 350.0),
    },
    "ph_lockout": {
        "ph": (7.5, 8.5),
        "ec": (1.3, 1.7),
        "temp": (23.0, 27.0),
        "n": (180.0, 220.0),
        "p": (330.0, 370.0),
        "k": (550.0, 650.0),
    },
    "over_dosed": {
        "ph": (5.8, 6.4),
        "ec": (2.8, 4.0),
        "temp": (24.0, 28.0),
        "n": (280.0, 350.0),
        "p": (450.0, 550.0),
        "k": (750.0, 900.0),
    },
    "under_dosed": {
        "ph": (6.0, 6.6),
        "ec": (0.1, 0.5),
        "temp": (24.0, 27.0),
        "n": (30.0, 60.0),
        "p": (50.0, 100.0),
        "k": (80.0, 150.0),
    },
}

def create_test_image(state_key, label):
    """Generates a simple colored image for the state."""
    img_dir = os.path.join("images", "seed_tests")
    os.makedirs(img_dir, exist_ok=True)
    
    filename = f"test_{state_key}.jpg"
    filepath = os.path.join(img_dir, filename)
    
    # Create a 400x400 image with the state's color
    color = STATES[state_key].get("color", (128, 128, 128))
    img = Image.new("RGB", (400, 400), color=color)
    
    # Add text label
    draw = ImageDraw.Draw(img)
    draw.text((20, 180), f"STATE: {label}", fill=(255, 255, 255))
    draw.text((20, 210), f"TEST IMAGE", fill=(255, 255, 255))
    
    img.save(filepath)
    return f"images/seed_tests/{filename}"


def get_or_create_experiment(db):
    exp = db.query(models.Experiment).filter(
        models.Experiment.experiment_id == EXPERIMENT_ID
    ).first()
    if not exp:
        exp = models.Experiment(
            experiment_id=EXPERIMENT_ID,
            bucket_label="Water",
            start_date=datetime.now().date()
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        print(f"  Created experiment: {EXPERIMENT_ID}")
    return exp


def clean_seeded_records(db):
    exp = db.query(models.Experiment).filter(
        models.Experiment.experiment_id == EXPERIMENT_ID
    ).first()
    if not exp:
        print("  Nothing to clean.")
        return

    readings = db.query(models.DailyReading).filter(
        models.DailyReading.experiment_id == exp.id
    ).all()

    for r in readings:
        if r.prediction:
            db.delete(r.prediction)
        db.delete(r)

    db.delete(exp)
    db.commit()
    print(f"  Cleaned {len(readings)} seeded reading(s).")


def seed_state(db, exp, state_key, offset_minutes=0, randomize=False):
    s = STATES[state_key]
    r_ranges = STATE_RANGES[state_key]
    ts = datetime.now() + timedelta(minutes=offset_minutes)

    if randomize:
        ph = round(random.uniform(*r_ranges["ph"]), 2)
        ec = round(random.uniform(*r_ranges["ec"]), 2)
        temp = round(random.uniform(*r_ranges["temp"]), 1)
        n = round(random.uniform(*r_ranges["n"]), 1)
        p = round(random.uniform(*r_ranges["p"]), 1)
        k = round(random.uniform(*r_ranges["k"]), 1)
    else:
        ph = s["ph"]
        ec = s["ec"]
        temp = s["temp"]
        n = s["n"]
        p = s["p"]
        k = s["k"]

    image_path = create_test_image(state_key, s["label"])

    reading = models.DailyReading(
        experiment_id=exp.id,
        ph=ph,
        ec=ec,
        water_temp=temp,
        ph_is_estimated=False,
        needs_ph_update=False,
        image_path=image_path,
        status="active",
        timestamp=ts
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    prediction = models.NPKPrediction(
        daily_reading_id=reading.id,
        predicted_n=n,
        predicted_p=p,
        predicted_k=k,
        prediction_date=ts
    )
    db.add(prediction)
    db.commit()

    print(f"  ✅ [{s['label']}]  pH={ph}  EC={ec}  N={n}  P={p}  K={k}")
    return reading


def main():
    parser = argparse.ArgumentParser(description="Seed dashboard classification states")
    parser.add_argument("--state", choices=list(STATES.keys()), help="Seed one specific state only")
    parser.add_argument("--random-state", action="store_true", help="Seed one randomly chosen state")
    parser.add_argument("--clean", action="store_true", help="Remove all seeded records first")
    parser.add_argument("--random", action="store_true", help="Randomize values within state ranges")
    parser.add_argument("--count", type=int, default=1, help="Number of records to seed per state")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle the order of states when seeding all")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.clean:
            print("🧹 Cleaning previous seeded records...")
            clean_seeded_records(db)

        print(f"🌱 Seeding dashboard states (random={args.random}, count={args.count})...")
        exp = get_or_create_experiment(db)

        if args.state:
            for i in range(args.count):
                seed_state(db, exp, args.state, offset_minutes=i, randomize=args.random)
        elif args.random_state:
            key = random.choice(list(STATES.keys()))
            for i in range(args.count):
                seed_state(db, exp, key, offset_minutes=i, randomize=args.random)
        else:
            state_keys = list(STATES.keys())
            if args.shuffle:
                random.shuffle(state_keys)
                print("🔀 Shuffled state order.")

            current_offset = 0
            for key in state_keys:
                for i in range(args.count):
                    seed_state(db, exp, key, offset_minutes=current_offset, randomize=args.random)
                    current_offset += 1

            latest = state_keys[-1]
            print(f"\n  👆 Latest record is '{STATES[latest]['label']}'")

        print("\n✅ Done.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
