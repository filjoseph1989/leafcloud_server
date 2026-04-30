import os

def delete_appledouble_files(root_dir="."):
    """
    Recursively deletes AppleDouble files (starting with ._).
    """
    deleted_count = 0
    print(f"🔍 Searching for AppleDouble files in: {os.path.abspath(root_dir)}")

    for root, dirs, files in os.walk(root_dir):
        # Avoid messing with the .git folder
        if ".git" in root:
            continue
            
        for filename in files:
            if filename.startswith("._"):
                file_path = os.path.join(root, filename)
                try:
                    os.remove(file_path)
                    print(f"✅ Deleted: {file_path}")
                    deleted_count += 1
                except Exception as e:
                    print(f"❌ Failed to delete {file_path}: {e}")

    print(f"\n✨ Cleanup complete. Total files deleted: {deleted_count}")

if __name__ == "__main__":
    delete_appledouble_files()
