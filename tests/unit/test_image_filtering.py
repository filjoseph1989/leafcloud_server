import os
import pytest
from image_filtering import is_macos_metadata, delete_macos_metadata

def test_is_macos_metadata():
    assert is_macos_metadata("._image.jpg") is True
    assert is_macos_metadata("image.jpg") is False
    assert is_macos_metadata(".DS_Store") is False

def test_delete_macos_metadata(tmp_path):
    # Create dummy files
    metadata_file = tmp_path / "._test.jpg"
    metadata_file.write_text("dummy content")
    regular_file = tmp_path / "test.jpg"
    regular_file.write_text("regular content")
    
    assert os.path.exists(metadata_file)
    assert os.path.exists(regular_file)
    
    deleted_count = delete_macos_metadata(str(tmp_path))
    
    assert deleted_count == 1
    assert not os.path.exists(metadata_file)
    assert os.path.exists(regular_file)

def test_is_corrupted_file(tmp_path):
    from image_filtering import is_corrupted_file
    
    # Create a small file
    small_file = tmp_path / "small.jpg"
    small_file.write_text("a" * 100) # 100 bytes
    
    # Create a large file
    large_file = tmp_path / "large.jpg"
    large_file.write_text("a" * 2000) # 2000 bytes
    
    assert is_corrupted_file(str(small_file), threshold=1000) is True
    assert is_corrupted_file(str(large_file), threshold=1000) is False

def test_delete_corrupted_files(tmp_path):
    from image_filtering import delete_corrupted_files
    
    small_file = tmp_path / "corrupted.jpg"
    small_file.write_text("too small")
    
    regular_file = tmp_path / "good.jpg"
    regular_file.write_text("a" * 2000)
    
    deleted_count = delete_corrupted_files(str(tmp_path), threshold=1000)
    
    assert deleted_count == 1
    assert not os.path.exists(small_file)
    assert os.path.exists(regular_file)

def test_calculate_greenness(mocker):
    import numpy as np
    from image_filtering import calculate_greenness
    
    # Create a 100x100 green image (BGR: 0, 255, 0)
    green_img = np.zeros((100, 100, 3), dtype=np.uint8)
    green_img[:, :, 1] = 255
    
    # Create a 100x100 black image
    black_img = np.zeros((100, 100, 3), dtype=np.uint8)
    
    mock_imread = mocker.patch("cv2.imread")
    
    # Test green image
    mock_imread.return_value = green_img
    assert calculate_greenness("dummy.jpg") == 100.0
    
    # Test black image
    mock_imread.return_value = black_img
    assert calculate_greenness("dummy.jpg") == 0.0

def test_is_mostly_green(mocker):
    from image_filtering import is_mostly_green
    
    mocker.patch("image_filtering.calculate_greenness", side_effect=[60.0, 10.0])
    
    assert is_mostly_green("green.jpg", threshold=50.0) is True
    assert is_mostly_green("not_green.jpg", threshold=50.0) is False

def test_process_image_batch(tmp_path, mocker):
    import shutil
    from image_filtering import process_image_batch
    
    # Create test directory and trash directory
    test_dir = tmp_path / "images"
    test_dir.mkdir()
    trash_dir = tmp_path / "temp_trash"
    trash_dir.mkdir()
    
    # 1. Metadata file (should be deleted)
    metadata_file = test_dir / "._meta.jpg"
    metadata_file.write_text("meta")
    
    # 2. Corrupted file (should be deleted)
    corrupted_file = test_dir / "corrupted.jpg"
    corrupted_file.write_text("small") # 5 bytes
    
    # 3. Non-green file (should be moved to trash)
    not_green_file = test_dir / "not_green.jpg"
    not_green_file.write_text("a" * 2000)
    
    # 4. Green file (should stay)
    green_file = test_dir / "green.jpg"
    green_file.write_text("a" * 2000)
    
    # 5. Nested image in subdirectory (should be processed)
    sub_dir = test_dir / "2026-04-16" / "Micro"
    sub_dir.mkdir(parents=True)
    nested_file = sub_dir / "nested.jpg"
    nested_file.write_text("a" * 2000)
    
    # Mock greenness: 10% for not_green, 90% for green, 90% for nested
    mocker.patch("image_filtering.calculate_greenness", side_effect=[10.0, 90.0, 90.0])
    
    stats = process_image_batch(
        str(test_dir), 
        str(trash_dir), 
        size_threshold=1000, 
        green_threshold=50.0
    )
    
    assert stats["deleted_metadata"] == 1
    assert stats["deleted_corrupted"] == 1
    assert stats["moved_to_trash"] == 1
    assert stats["kept"] == 2 # green.jpg + nested.jpg
    assert stats["total_processed"] == 5
    
    assert not os.path.exists(metadata_file)
    assert not os.path.exists(corrupted_file)
    assert not os.path.exists(not_green_file)
    assert os.path.exists(green_file)
    assert os.path.exists(nested_file)
    
    # Check if a file with the name exists in trash (it should have a UUID prefix)
    trash_files = os.listdir(trash_dir)
    assert any(f.endswith("_not_green.jpg") for f in trash_files)

def test_process_image_batch_with_logging(tmp_path, mocker):
    import shutil
    from image_filtering import process_image_batch
    from models import AutomatedActionLog
    
    test_dir = tmp_path / "images"
    test_dir.mkdir()
    trash_dir = tmp_path / "temp_trash"
    trash_dir.mkdir()
    
    # Create a non-green file (should be moved and logged)
    not_green_file = test_dir / "bad.jpg"
    not_green_file.write_text("a" * 2000)
    
    # Mock greenness
    mocker.patch("image_filtering.calculate_greenness", return_value=10.0)
    
    # Mock DB Session
    mock_db = mocker.Mock()
    
    stats = process_image_batch(
        str(test_dir), 
        str(trash_dir), 
        size_threshold=1000, 
        green_threshold=50.0,
        db=mock_db
    )
    
    assert stats["moved_to_trash"] == 1
    
    # Verify that mock_db.add was called
    mock_db.add.assert_called_once()
    log_entry = mock_db.add.call_args[0][0]
    assert isinstance(log_entry, AutomatedActionLog)
    assert log_entry.filename == "bad.jpg"
    assert log_entry.action_type == "move_to_trash"
    assert log_entry.reason == "low_greenness"
    assert log_entry.metric_value == 10.0
    assert log_entry.original_path == str(not_green_file)
    
    # Verify current_path has UUID and ends with filename
    assert log_entry.current_path.startswith(str(trash_dir))
    assert "_bad.jpg" in log_entry.current_path
    
    # Verify commit was called
    mock_db.commit.assert_called_once()
