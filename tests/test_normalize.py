from beeagent_module.core.normalize import normalize_bullets


def test_normalize_bullets_keeps_existing() -> None:
    text = "• a\n• b"
    assert normalize_bullets(text) == "• a\n• b"


def test_normalize_bullets_adds_bullets() -> None:
    text = "line1\nline2"
    assert normalize_bullets(text) == "• line1\n• line2"
