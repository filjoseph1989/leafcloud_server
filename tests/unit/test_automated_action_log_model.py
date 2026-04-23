import pytest
from sqlalchemy.orm import Session
from models import AutomatedActionLog
from datetime import datetime

def test_create_automated_action_log(db_session: Session):
    """
    Test that we can create and persist an AutomatedActionLog entry.
    """
    log_entry = AutomatedActionLog(
        filename="test_image.jpg",
        original_path="images/2026-04-18/test_image.jpg",
        current_path="images/temp_trash/test_image.jpg",
        action_type="move_to_trash",
        reason="low_greenness",
        metric_value=41.12
    )
    db_session.add(log_entry)
    db_session.commit()
    db_session.refresh(log_entry)

    assert log_entry.id is not None
    assert log_entry.filename == "test_image.jpg"
    assert log_entry.action_type == "move_to_trash"
    assert isinstance(log_entry.timestamp, datetime)
