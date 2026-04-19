import pytest

def test_import_image_info():
    try:
        from schemas.images import ImageInfo
        assert ImageInfo is not None
    except ImportError:
        pytest.fail("Could not import ImageInfo from schemas.images")

def test_import_login_request():
    try:
        from schemas.images import LoginRequest
        assert LoginRequest is not None
    except ImportError:
        pytest.fail("Could not import LoginRequest from schemas.images")
