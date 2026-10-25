#!/usr/bin/env python3
"""
pivitLABS ÖTSV Tool – Standalone Desktop App Launcher (https://pivitlabs.com)

Starts the local FastAPI backend in a background thread, ensures all user data
(working copy SQLite database, cloud folder synchronization, .env configuration, logs)
is stored persistently, and opens the application in a native OS WebView window
(pywebview – WebKit on macOS, Edge WebView2 on Windows) that behaves like an
installed Progressive Web App (PWA).
When the window is closed, the database is safely synced back to the cloud folder
(if configured) and the background server shuts down cleanly.
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
    Determine the persistent directory for working copy database (data/adsi.db),
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
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def wait_for_server(host: str, port: int, timeout_sec: float = 15.0) -> bool:
    """Block until the local FastAPI server accepts connections."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if is_port_in_use(host, port):
            return True
        time.sleep(0.15)
    return False


def main() -> None:
    data_dir = setup_environment()

    # Import app and settings after working directory is configured
    from app.config import settings
    from app.main import app
    from app.services.storage_service import register_webview_window, shutdown_storage
    import uvicorn

    host = settings.HOST
    port = settings.PORT
    url = f"http://{host}:{port}"

    print("=" * 64)
    print("  pivitLABS ÖTSV Tool (https://pivitlabs.com)")
    print(f"  Arbeitsordner: {data_dir}")
    print(f"  App-Server:    {url}")
    print(f"  Admin-Center:  {url}/adsi-admin")
    print("=" * 64)

    use_browser_mode = "--browser" in sys.argv
    server_instance = None

    # Start FastAPI server in a background daemon thread if not already running
    if not is_port_in_use(host, port):
        uv_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            log_config=None,
        )
        server_instance = uvicorn.Server(uv_config)
        server_thread = threading.Thread(target=server_instance.run, daemon=True)
        server_thread.start()
        wait_for_server(host, port, timeout_sec=15.0)

    if not use_browser_mode:
        try:
            import webview

            window = webview.create_window(
                title="pivitLABS ÖTSV Tool",
                url=url,
                width=1340,
                height=880,
                min_size=(900, 620),
                text_select=True,
            )
            register_webview_window(window)

            def on_closed():
                print("App-Fenster geschlossen – synchronisiere Datenbank & beende Server...")
                try:
                    shutdown_storage()
                except Exception as e:
                    print(f"Warnung beim Cloud-Sync: {e}")
                if server_instance is not None:
                    server_instance.should_exit = True

            window.events.closed += on_closed
            webview.start()

            # Wait briefly for uvicorn lifespan shutdown to finish cleanly
            if server_instance is not None:
                server_instance.should_exit = True
                time.sleep(0.4)
            return
        except Exception as e:
            print(f"Hinweis: Native WebView konnte nicht gestartet werden ({e}) – öffne Standard-Browser...")

    # Fallback: Browser mode if --browser flag was passed or pywebview unavailable
    webbrowser.open(url)
    if server_instance is not None:
        try:
            while not server_instance.should_exit:
                time.sleep(0.5)
        except KeyboardInterrupt:
            server_instance.should_exit = True
            shutdown_storage()


if __name__ == "__main__":
    main()
