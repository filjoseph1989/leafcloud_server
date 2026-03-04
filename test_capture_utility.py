import pytest
from unittest.mock import MagicMock, patch
import os

# We'll import from main once we add it, for now we mock the entire module or just the function
# But TDD says we should have it imported and it should fail.

def test_capture_frame_success():
    from main import capture_frame
    
    # Mock cv2.VideoCapture
    with patch('cv2.VideoCapture') as mock_video_capture, \
         patch('cv2.imwrite') as mock_imwrite:
        
        mock_cap = MagicMock()
        mock_video_capture.return_value = mock_cap
        
        # mock_cap.read() returns (True, frame)
        mock_cap.read.return_value = (True, "mock_frame")
        mock_imwrite.return_value = True
        
        result = capture_frame("udp://mock_url", "images/test.jpg")
        
        assert result is True
        mock_video_capture.assert_called_once_with("udp://mock_url")
        mock_cap.read.assert_called()
        mock_imwrite.assert_called_once_with("images/test.jpg", "mock_frame")
        mock_cap.release.assert_called_once()

def test_capture_frame_failure():
    from main import capture_frame
    
    with patch('cv2.VideoCapture') as mock_video_capture:
        mock_cap = MagicMock()
        mock_video_capture.return_value = mock_cap
        
        # mock_cap.read() returns (False, None)
        mock_cap.read.return_value = (False, None)
        
        result = capture_frame("udp://mock_url", "images/test.jpg")
        
        assert result is False
        mock_cap.release.assert_called_once()
