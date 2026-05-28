"""Unit tests for activities module — verify coaching-related additions."""

from activities import set_coach_evaluation, post_activity_message


def test_set_coach_evaluation_is_callable():
    """set_coach_evaluation function exists and is callable."""
    assert callable(set_coach_evaluation)


def test_post_activity_message_is_callable():
    """post_activity_message function exists and is callable."""
    assert callable(post_activity_message)
