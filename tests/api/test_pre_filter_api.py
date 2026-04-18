import pytest
from unittest.mock import patch

def test_pre_filter_images_endpoint(client, mocker):
    """Verify that the pre-filter endpoint calls process_image_batch and returns stats."""
    
    mock_stats = {
        "deleted_metadata": 2,
        "deleted_corrupted": 1,
        "moved_to_trash": 5,
        "kept": 10,
        "total_processed": 18
    }
    
    # Mock the utility function
    mock_process = mocker.patch("image_filtering.process_image_batch", return_value=mock_stats)
    
    payload = {
        "size_threshold": 2000,
        "green_threshold": 45.5
    }
    
    # We'll use the /api/v1/images/pre-filter endpoint as per spec
    response = client.post("/api/v1/images/pre-filter", json=payload)
    
    # Should fail if not implemented (404) or implemented differently
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "success"
    assert data["stats"] == mock_stats
    
    # Verify mock was called with correct parameters
    mock_process.assert_called_once()
    args, kwargs = mock_process.call_args
    assert args[2] == 2000 # size_threshold
    assert args[3] == 45.5 # green_threshold
