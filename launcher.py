#!/usr/bin/env python3
"""
pivitLABS ÖTSV Tool – Desktop Launcher (https://pivitlabs.com)

Starts the local FastAPI server on 127.0.0.1:8000, ensures all user data
(SQLite database, .env configuration, logs) is stored persistently, and
automatically opens the application in the default web browser.
"""
import os
import sys
import time
import shutil
import socket
import threading
import webbrowser
from pathlib import Path


APP_DIR_NAME = "pivitLABS-OETSV-Tool"


def get_persistent_data_dir() -> Path:
    """
    Determine the persistent directory for database (data/adsi.db),
    configuration (.env), and logs (logs/).
    - When bundled as a PyInstaller app (.app / .exe), uses the OS user data folder
      so updates or read-only app bundles never lose data.
    - When run from source, uses the project root directory.
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
        elif sys.platform == "win32":
            appdata = os.environ.get("APPDATA")
            base = (Path(appdata) if appdata else Path.home() / "AppData" / "Roaming") / APP_DIR_NAME
        else:
            base = Path.home() / ".local" / "share" / APP_DIR_NAME
        return base
    return Path(__file__).resolve().parent


def setup_environment() -> Path:
    """Ensure persistent folders, SSL certs, and .env exist, and switch working directory."""
    data_dir = get_persistent_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "data").mkdir(exist_ok=True)
    (data_dir / "logs").mkdir(exist_ok=True)

    # Redirect stdout/stderr if running inside a windowless bundle (.app / .exe)
    if sys.stdout is None or sys.stderr is None:
        log_file = open(data_dir / "logs" / "launcher.log", "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = log_file
        if sys.stderr is None:
            sys.stderr = log_file

    # Ensure bundled SSL certificates are used by httpx / ssl in PyInstaller bundles
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass

    env_file = data_dir / ".env"
    if not env_file.exists():
        # Copy default .env.example if available
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        example_env = bundle_dir / ".env.example"
        if example_env.exists():
            shutil.copyfile(example_env, env_file)
            try:
                os.chmod(env_file, 0o600)
            except OSError:
                pass

    os.chdir(data_dir)
    return data_dir


def is_port_in_use(host: str, port: int) -> bool:
    """Check if the local server is already listening on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def open_browser_when_ready(url: str, host: str, port: int) -> None:
    """Wait until the FastAPI server accepts connections, then open the browser."""
    for _ in range(50):
        if is_port_in_use(host, port):
            time.sleep(0.2)
            webbrowser.open(url)
            return
        time.sleep(0.2)


def main() -> None:
    data_dir = setup_environment()

    # Import app and settings after working directory is configured
    from app.config import settings
    from app.main import app
    import uvicorn

    host = settings.HOST
    port = settings.PORT
    url = f"http://{host}:{port}"

    print("=" * 64)
    print("  pivitLABS ÖTSV Tool (https://pivitlabs.com)")
    print(f"  Datenordner: {data_dir}")
    print(f"  Turnierportal: {url}")
    print(f"  Admin-Center:  {url}/adsi-admin")
    print("  Hinweis: Alle Daten & Einstellungen bleiben automatisch gespeichert.")
    print("=" * 64)

    # If the server is already running, just open the browser window
    if is_port_in_use(host, port):
        print(f"Server läuft bereits auf {url} – öffne Browser...")
        webbrowser.open(url)
        return

    # Open browser automatically once server is ready
    threading.Thread(
        target=open_browser_when_ready,
        args=(url, host, port),
        daemon=True
    ).start()

    uvicorn.run(app, host=host, port=port, log_level="info", log_config=None)


if __name__ == "__main__":
    main()
