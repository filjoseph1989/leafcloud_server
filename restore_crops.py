import os
import shutil
from sqlalchemy.orm import Session
from database import SessionLocal
import models

def list_trashed_crops(db):
    logs = db.query(models.AutomatedActionLog).filter(
        models.AutomatedActionLog.reason == "low_greenness_crop",
        models.AutomatedActionLog.action_type == "move_to_trash"
    ).order_by(models.AutomatedActionLog.id.desc()).limit(50).all()

    if not logs:
        print("\nNo trashed crops found in the logs.")
        return

    print("\n--- RECENT TRASHED CROPS (Last 50) ---")
    print(f"{'ID':<6} | {'Greenness':<10} | {'Original Filename'}")
    print("-" * 60)
    for log in logs:
        print(f"{log.id:<6} | {log.metric_value:<10.2f} | {log.filename}")
    
    total = db.query(models.AutomatedActionLog).filter(
        models.AutomatedActionLog.reason == "low_greenness_crop",
        models.AutomatedActionLog.action_type == "move_to_trash"
    ).count()
    print(f"\nTotal items in trash: {total}")

def restore_by_ids(db, id_list):
    restored = 0
    for log_id in id_list:
        log = db.query(models.AutomatedActionLog).filter(models.AutomatedActionLog.id == log_id).first()
        if not log:
            print(f"ID {log_id} not found.")
            continue
        
        if restore_file(log):
            log.action_type = "restored"
            restored += 1
    
    db.commit()
    print(f"\nSuccessfully restored {restored} crops.")

def restore_by_threshold(db, threshold):
    logs = db.query(models.AutomatedActionLog).filter(
        models.AutomatedActionLog.reason == "low_greenness_crop",
        models.AutomatedActionLog.action_type == "move_to_trash",
        models.AutomatedActionLog.metric_value >= threshold
    ).all()

    if not logs:
        print(f"No crops found with greenness >= {threshold}%")
        return

    print(f"Found {len(logs)} crops. Restoring...")
    restored = 0
    for log in logs:
        if restore_file(log):
            log.action_type = "restored"
            restored += 1
    
    db.commit()
    print(f"\nSuccessfully restored {restored} crops.")

def restore_file(log):
    # Paths are stored relative to BASE_DIR in the script I wrote earlier
    base_dir = os.path.dirname(os.path.abspath(__file__))
    current_abs = os.path.join(base_dir, log.current_path)
    original_abs = os.path.join(base_dir, log.original_path)

    if not os.path.exists(current_abs):
        print(f"File not found in trash: {log.current_path}")
        return False

    try:
        os.makedirs(os.path.dirname(original_abs), exist_ok=True)
        shutil.move(current_abs, original_abs)
        return True
    except Exception as e:
        print(f"Error moving {log.filename}: {e}")
        return False

def main():
    db = SessionLocal()
    try:
        while True:
            print("\n=== CROP RESTORATION TOOL ===")
            print("1. List recent trashed crops")
            print("2. Restore by ID(s) (e.g., 1,2,5 or 10-20)")
            print("3. Restore all above a specific Greenness %")
            print("4. Exit")
            
            choice = input("\nSelect an option: ")

            if choice == '1':
                list_trashed_crops(db)
            elif choice == '2':
                val = input("Enter ID(s) or range (e.g. 101,102 or 105-110): ")
                ids = []
                try:
                    for part in val.split(','):
                        if '-' in part:
                            start, end = map(int, part.split('-'))
                            ids.extend(range(start, end + 1))
                        else:
                            ids.append(int(part.strip()))
                    restore_by_ids(db, ids)
                except ValueError:
                    print("Invalid input format.")
            elif choice == '3':
                try:
                    t = float(input("Restore everything with Greenness >= %: "))
                    restore_by_threshold(db, t)
                except ValueError:
                    print("Please enter a valid number.")
            elif choice == '4':
                break
            else:
                print("Invalid choice.")

    finally:
        db.close()

if __name__ == "__main__":
    main()
