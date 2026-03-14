import pytest

@pytest.mark.skip(reason="Streaming endpoint hangs in TestClient without active frame generation")
def test_video_feed_exists(client):
    # Just verify the headers to avoid hanging on the stream content
    with client.stream("GET", "/video_feed") as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "multipart/x-mixed-replace; boundary=frame"
