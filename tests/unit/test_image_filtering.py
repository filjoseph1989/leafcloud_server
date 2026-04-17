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
