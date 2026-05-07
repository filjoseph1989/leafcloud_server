import os
import time
import errno

def delete_with_retry(file_path, max_retries=3, delay=1.0):
    """
    Attempts to delete a file with retries for specific errors like Stale NFS handle.
    """
    for attempt in range(max_retries):
        try:
            os.remove(file_path)
            return True, None
        except OSError as e:
            # Error 70 is ESTALE (Stale NFS file handle)
            if e.errno == 70 or e.errno == getattr(errno, 'ESTALE', 116):
                if attempt < max_retries - 1:
                    time.sleep(delay * (attempt + 1)) # Exponential-ish backoff
                    continue
            return False, e
    return False, "Max retries reached"

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
            
        # Also check for hidden folders starting with ._
        for dirname in list(dirs):
            if dirname.startswith("._"):
                dir_path = os.path.join(root, dirname)
                success, error = delete_with_retry(dir_path)
                if success:
                    print(f"✅ Deleted (Dir): {dir_path}")
                    deleted_count += 1
                else:
                    print(f"❌ Failed to delete directory {dir_path}: {error}")
                dirs.remove(dirname) # Don't walk into it

        for filename in files:
            if filename.startswith("._"):
                file_path = os.path.join(root, filename)
                success, error = delete_with_retry(file_path)
                if success:
                    print(f"✅ Deleted: {file_path}")
                    deleted_count += 1
                else:
                    print(f"❌ Failed to delete {file_path}: {error}")

    print(f"\n✨ Cleanup complete. Total files deleted: {deleted_count}")

if __name__ == "__main__":
    delete_appledouble_files()
