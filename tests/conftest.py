import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def default_test_club_settings(monkeypatch, tmp_path):
    """Ensure unit tests always run against the default test club (TSC Musterverein) regardless of local .env."""
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "CLUB_NAME", "TSC Musterverein")
    monkeypatch.setattr(settings, "CLUB_SHORT", "Musterverein")
    monkeypatch.setattr(settings, "CLUB_KEYWORDS", "")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    test_storage_file = tmp_path / "storage_settings.json"
    monkeypatch.setattr("app.services.storage_service.get_storage_settings_path", lambda: test_storage_file)
