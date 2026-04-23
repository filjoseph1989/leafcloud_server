import pytest
from unittest.mock import MagicMock, patch
import os
import cv2

def test_capture_frame_success():
    from controllers.iot_controller import capture_frame
    
    # Mock VIDEO_MANAGER in controllers.iot_controller
    with patch('controllers.iot_controller.VIDEO_MANAGER') as mock_vm, \
         patch('cv2.imwrite') as mock_imwrite:
        
        mock_vm.get_latest_frame.return_value = "mock_frame"
        mock_imwrite.return_value = True
        
        # Updated signature: only output_path
        result = capture_frame("images/test.jpg")
        
        assert result is True
        mock_vm.get_latest_frame.assert_called_once()
        mock_imwrite.assert_called_once_with("images/test.jpg", "mock_frame")

def test_capture_frame_failure():
    from controllers.iot_controller import capture_frame
    
    with patch('controllers.iot_controller.VIDEO_MANAGER') as mock_vm:
        mock_vm.get_latest_frame.return_value = None
        
        # Updated signature: only output_path
        result = capture_frame("images/test.jpg")
        
        assert result is False
        mock_vm.get_latest_frame.assert_called_once()
