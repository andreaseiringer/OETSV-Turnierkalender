#!/usr/bin/env python3
"""
Build & Packaging Script for pivitLABS ÖTSV Tool (https://pivitlabs.com)

Creates ready-to-download customer installers in the `release/` folder:
1. Native Standalone Desktop App (pywebview + PWA):
   - macOS: `release/pivitLABS-OETSV-Tool-macOS.dmg` (Drag-and-Drop to /Applications) & `release/pivitLABS-OETSV-Tool-macOS.zip`
   - Windows: `release/pivitLABS-OETSV-Tool-Windows-Setup.exe` (via Inno Setup if ISCC is installed) & `release/pivitLABS-OETSV-Tool-Windows.zip`
2. Universal PC & Mac Starter Package:
   - `release/pivitLABS-OETSV-Tool-Universal-PC-Mac.zip`
"""
import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path


LIESMICH_TEXT = """========================================================================
  pivitLABS ÖTSV Tool – Installations- & Startanleitung (v1.5.0)
  Copyright pivitlabs (https://pivitlabs.com)
========================================================================

Vielen Dank für das Herunterladen des pivitLABS ÖTSV Tools!
Das Tool läuft als eigenständige Desktop-App (App-Fenster ohne Browser-Leiste)
und unterstützt sowohl lokale Speicherung als auch Cloud-Ordner (iCloud Drive,
Google Drive, OneDrive).

SO INSTALLIERST & STARTEST DU DIE APP:
------------------------------------------------------------------------

[macOS – DMG Installer / Eigenständige App]
1. Öffne "pivitLABS-OETSV-Tool-macOS.dmg" (oder entpacke die ZIP-Datei).
2. Ziehe "pivitLABS OETSV Tool.app" in deinen "Programme"-Ordner (Applications).
3. Starte "pivitLABS OETSV Tool.app" aus dem Programme-Ordner oder Launchpad.
   -> Hinweis beim allerersten Start auf macOS:
      Falls macOS meldet, dass der Entwickler nicht verifiziert werden kann,
      mache einmalig einen Rechtsklick (Ctrl+Klick) auf das App-Symbol und
      wähle "Öffnen" -> "Öffnen".
4. Die App öffnet sich als eigenständiges Programmfenster. Beim Schließen des
   Fensters wird die Datenbank automatisch gesichert und der Server beendet.

[Windows – Setup-Installer (.exe) oder Portable ZIP]
1. Starte "pivitLABS-OETSV-Tool-Windows-Setup.exe" und folge dem Assistenten
   (legt automatisch ein Startmenü- & Desktop-Symbol an).
   Alternativ im ZIP-Paket: Starte "pivitLABS OETSV Tool.exe".
2. Die App öffnet sich als eigenständiges Programmfenster.

------------------------------------------------------------------------
CLOUD-SPEICHER (iCloud Drive, Google Drive, OneDrive) & VEREIN:
------------------------------------------------------------------------
- Beim ersten Start (sowie jederzeit im Admin-Center unter "Datenspeicher &
  Cloud-Synchronisation") kannst du wählen:
  * Lokal auf diesem Gerät
  * Cloud-Ordner (iCloud Drive, Google Drive, OneDrive oder eigener Ordner)
- Arbeitskopie-Prinzip:
  Beim Start lädt die App die Datenbank in eine schnelle lokale Arbeitskopie
  und speichert sie nach jedem Abruf sowie beim Schließen des Fensters als
  konsistente Einzeldatei (adsi.db) zurück in deinen Cloud-Ordner.
- Im Cloud-Ordner werden standardmäßig die SQLite-Datenbank (adsi.db) und
  deine Vereinseinstellungen (cloud_config.json) abgelegt. Optional kannst du
  per Schalter auch die IMAP-Postfach-Einstellungen in der Cloud mitspeichern.
========================================================================
"""

WINDOWS_SHORTCUT_VBS = """Set oWS = WScript.CreateObject("WScript.Shell")
sDesktop = oWS.SpecialFolders("Desktop")
sScriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sExePath = sScriptDir & "\\pivitLABS OETSV Tool.exe"
sBatPath = sScriptDir & "\\Start_OETSV_Tool.bat"

Set oLink = oWS.CreateShortcut(sDesktop & "\\pivitLABS ÖTSV Tool.lnk")
If CreateObject("Scripting.FileSystemObject").FileExists(sExePath) Then
    oLink.TargetPath = sExePath
Else
    oLink.TargetPath = sBatPath
End If
oLink.WorkingDirectory = sScriptDir
oLink.Description = "pivitLABS ÖTSV Tool starten"
oLink.Save

MsgBox "Das Desktop-Icon 'pivitLABS ÖTSV Tool' wurde erfolgreich auf deinem Desktop erstellt!", 64, "pivitLABS ÖTSV Tool"
"""


def create_universal_zip(project_root: Path, release_dir: Path) -> Path:
    """Create a lightweight Universal ZIP for Windows & macOS with 1-click starters."""
    zip_path = release_dir / "pivitLABS-OETSV-Tool-Universal-PC-Mac.zip"
    root_folder = "pivitLABS-OETSV-Tool"

    include_files = [
        ".env.example",
        "LICENSE",
        "README.md",
        "requirements.txt",
        "launcher.py",
        "Start_OETSV_Tool.command",
        "Start_OETSV_Tool.bat",
    ]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root_folder}/LIESMICH.txt", LIESMICH_TEXT)
        zf.writestr(f"{root_folder}/Desktop-Icon-erstellen.vbs", WINDOWS_SHORTCUT_VBS)

        for rel in include_files:
            src = project_root / rel
            if src.exists():
                zf.write(src, f"{root_folder}/{rel}")

        app_dir = project_root / "app"
        for path in app_dir.rglob("*"):
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            if path.is_file():
                rel_path = path.relative_to(project_root)
                zf.write(path, f"{root_folder}/{rel_path.as_posix()}")

    return zip_path


def find_iscc_executable() -> str | None:
    """Locate Inno Setup Compiler (ISCC.exe) on Windows."""
    if shutil.which("ISCC"):
        return shutil.which("ISCC")
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def main() -> None:
    project_root = Path(__file__).resolve().parent
    release_dir = project_root / "release"
    release_dir.mkdir(exist_ok=True)

    # Ensure icons exist before building
    try:
        from scripts.generate_icons import generate_all_icons
        generate_all_icons(project_root)
    except Exception as e:
        print(f"Hinweis bei Icon-Generierung: {e}")

    os.environ["PYINSTALLER_CONFIG_DIR"] = str(project_root / "build" / ".pyinstaller_cache")
    (project_root / "LIESMICH.txt").write_text(LIESMICH_TEXT, encoding="utf-8")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller wird installiert...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    sep = ";" if sys.platform == "win32" else ":"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", "pivitLABS OETSV Tool",
        "--onedir",
        "--windowed",
        "--add-data", f"{project_root / 'app' / 'static'}{sep}app/static",
        "--add-data", f"{project_root / '.env.example'}{sep}.",
        "--collect-data", "tzdata",
        "--collect-data", "certifi",
        "--collect-all", "webview",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "app.main",
        "--hidden-import", "webview",
    ]

    icns_file = project_root / "app" / "static" / "img" / "app-icon.icns"
    ico_file = project_root / "app" / "static" / "img" / "app-icon.ico"

    if sys.platform == "darwin":
        cmd.extend(["--osx-bundle-identifier", "com.pivitlabs.oetsvtool"])
        if icns_file.exists():
            cmd.extend(["--icon", str(icns_file)])
    elif sys.platform == "win32":
        if ico_file.exists():
            cmd.extend(["--icon", str(ico_file)])

    cmd.append(str(project_root / "launcher.py"))

    print("1/3 Baue eigenständige Desktop-App (pywebview + FastAPI) mit PyInstaller...")
    subprocess.check_call(cmd, cwd=str(project_root))

    print("2/3 Erstelle kundenfertige Installer-Pakete in release/...")
    dist_dir = project_root / "dist"

    if sys.platform == "darwin":
        app_bundle = dist_dir / "pivitLABS OETSV Tool.app"
        staging_dir = dist_dir / "pivitLABS-OETSV-Tool-macOS"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True)

        shutil.copytree(app_bundle, staging_dir / "pivitLABS OETSV Tool.app", symlinks=True)
        (staging_dir / "LIESMICH.txt").write_text(LIESMICH_TEXT, encoding="utf-8")

        # 1. Create macOS ZIP using ditto
        mac_zip = release_dir / "pivitLABS-OETSV-Tool-macOS.zip"
        if mac_zip.exists():
            mac_zip.unlink()
        subprocess.check_call(["ditto", "-c", "-k", "--keepParent", str(staging_dir), str(mac_zip)])

        # 2. Create macOS Drag-and-Drop .dmg Installer with /Applications symlink
        dmg_staging = dist_dir / "dmg_staging"
        if dmg_staging.exists():
            shutil.rmtree(dmg_staging)
        dmg_staging.mkdir(parents=True)
        shutil.copytree(app_bundle, dmg_staging / "pivitLABS OETSV Tool.app", symlinks=True)
        (dmg_staging / "LIESMICH.txt").write_text(LIESMICH_TEXT, encoding="utf-8")
        try:
            os.symlink("/Applications", dmg_staging / "Applications")
        except OSError:
            pass

        mac_dmg = release_dir / "pivitLABS-OETSV-Tool-macOS.dmg"
        if mac_dmg.exists():
            mac_dmg.unlink()
        try:
            if shutil.which("diskutil"):
                subprocess.check_call([
                    "diskutil", "image", "create", "from",
                    "--format", "UDZO",
                    "--volumeName", "pivitLABS OETSV Tool",
                    str(dmg_staging),
                    str(mac_dmg),
                ])
            elif shutil.which("hdiutil"):
                subprocess.check_call([
                    "hdiutil", "create",
                    "-volname", "pivitLABS OETSV Tool",
                    "-srcfolder", str(dmg_staging),
                    "-ov",
                    "-format", "UDZO",
                    str(mac_dmg),
                ])
        except subprocess.CalledProcessError as e:
            print(f"Hinweis: DMG-Erstellung fehlgeschlagen ({e}) – macOS App-ZIP liegt bereit.")
        finally:
            shutil.rmtree(dmg_staging, ignore_errors=True)

    elif sys.platform == "win32":
        win_app_dir = dist_dir / "pivitLABS OETSV Tool"
        (win_app_dir / "LIESMICH.txt").write_text(LIESMICH_TEXT, encoding="utf-8")
        (win_app_dir / "Desktop-Icon-erstellen.vbs").write_text(WINDOWS_SHORTCUT_VBS, encoding="utf-8")

        # 1. Portable Windows ZIP
        win_zip = release_dir / "pivitLABS-OETSV-Tool-Windows.zip"
        if win_zip.exists():
            win_zip.unlink()
        shutil.make_archive(
            str(release_dir / "pivitLABS-OETSV-Tool-Windows"),
            "zip",
            root_dir=str(dist_dir),
            base_dir="pivitLABS OETSV Tool",
        )

        # 2. Windows Native Setup Installer (.exe) via Inno Setup
        iscc = find_iscc_executable()
        iss_file = project_root / "installer.iss"
        if iscc and iss_file.exists():
            print(f"Erstelle Windows Setup-Installer mit Inno Setup ({iscc})...")
            subprocess.check_call([iscc, str(iss_file)], cwd=str(project_root))
        else:
            print("Hinweis: Inno Setup (ISCC.exe) nicht gefunden – Windows-ZIP wurde erstellt.")

    print("3/3 Erstelle universelles PC & Mac Paket...")
    create_universal_zip(project_root, release_dir)

    print("\n" + "=" * 68)
    print("  FERTIG! Folgende Kunden-Installer liegen bereit in: release/")
    print("=" * 68)
    for f in sorted(release_dir.iterdir()):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  -> {f.name:<48} ({size_mb:.1f} MB)")
    print("=" * 68)


if __name__ == "__main__":
    main()
