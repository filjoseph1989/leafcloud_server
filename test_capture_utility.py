import pytest
from unittest.mock import MagicMock, patch
import os

def test_capture_frame_success():
    from main import capture_frame
    
    # Mock video_manager
    with patch('main.video_manager') as mock_vm, \
         patch('cv2.imwrite') as mock_imwrite:
        
        mock_vm.get_latest_frame.return_value = "mock_frame"
        mock_imwrite.return_value = True
        
        result = capture_frame("udp://mock_url", "images/test.jpg")
        
        assert result is True
        mock_vm.get_latest_frame.assert_called_once()
        mock_imwrite.assert_called_once_with("images/test.jpg", "mock_frame")

def test_capture_frame_failure():
    from main import capture_frame
    
    with patch('main.video_manager') as mock_vm:
        mock_vm.get_latest_frame.return_value = None
        
        result = capture_frame("udp://mock_url", "images/test.jpg")
        
        assert result is False
        mock_vm.get_latest_frame.assert_called_once()
