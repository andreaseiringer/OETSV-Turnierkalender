import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def default_test_club_settings(monkeypatch):
    """Ensure unit tests always run against the default test club (TSC Musterverein) regardless of local .env."""
    monkeypatch.setattr(settings, "CLUB_NAME", "TSC Musterverein")
    monkeypatch.setattr(settings, "CLUB_SHORT", "Musterverein")
    monkeypatch.setattr(settings, "CLUB_KEYWORDS", "")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
