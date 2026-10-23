import os
from app.services.config_service import update_env_file

def test_update_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_PORT=8000\nIMAP_ENABLED=false\nIMAP_SERVER=old.server.com\n")

    update_env_file({
        "IMAP_ENABLED": "true",
        "IMAP_SERVER": "new.server.com",
        "IMAP_USER": "test@example.com"
    }, env_path=str(env_file))

    content = env_file.read_text()
    assert "APP_PORT=8000" in content
    assert "IMAP_ENABLED=true" in content
    assert "IMAP_SERVER=new.server.com" in content
    assert "IMAP_USER=test@example.com" in content
    assert "IMAP_ENABLED=false" not in content
    assert "old.server.com" not in content

def test_update_env_file_prevents_newline_injection(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CLUB_NAME=TSC Musterverein\n")

    update_env_file({
        "CLUB_NAME": "My Club\nINJECTED_KEY=evil_value\r\n"
    }, env_path=str(env_file))

    lines = env_file.read_text().splitlines()
    assert len(lines) == 1
    assert lines[0] == "CLUB_NAME=My ClubINJECTED_KEY=evil_value"

