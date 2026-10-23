#!/usr/bin/env python3
"""
Build & Packaging Script for pivitLABS ÖTSV Tool (https://pivitlabs.com)

Creates ready-to-download customer packages in the `release/` folder:
1. Native Desktop App via PyInstaller:
   - macOS: `release/pivitLABS-OETSV-Tool-macOS.zip` & `release/pivitLABS-OETSV-Tool-macOS.dmg`
   - Windows: `release/pivitLABS-OETSV-Tool-Windows.zip` (incl. `pivitLABS OETSV Tool.exe` + Desktop-Shortcut creator)
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
  pivitLABS ÖTSV Tool – Installations- & Startanleitung
  Copyright pivitlabs (https://pivitlabs.com)
========================================================================

Vielen Dank für das Herunterladen des pivitLABS ÖTSV Tools!

SO EINFACH STARTEST DU DAS TOOL:
------------------------------------------------------------------------

[macOS – Eigenständige App]
1. Entpacke die ZIP-Datei (oder öffne die DMG-Datei).
2. Ziehe "pivitLABS OETSV Tool.app" in deinen "Programme"-Ordner oder
   direkt auf deinen Schreibtisch (Desktop).
3. Doppelklicke auf "pivitLABS OETSV Tool.app".
   -> Hinweis beim allerersten Start auf macOS:
      Falls macOS meldet, dass der Entwickler nicht verifiziert werden kann,
      mache einmalig einen Rechtsklick (Ctrl+Klick) auf das App-Symbol und
      wähle "Öffnen" -> "Öffnen".
4. Dein Browser öffnet sich automatisch unter http://127.0.0.1:8000

[Windows – Eigenständige App (.exe)]
1. Entpacke die ZIP-Datei in einen beliebigen Ordner (z.B. Dokumente).
2. Doppelklicke auf "Desktop-Icon-erstellen.vbs" (legt automatisch ein
   Start-Symbol auf deinem Desktop an) ODER starte direkt
   "pivitLABS OETSV Tool.exe".
3. Dein Browser öffnet sich automatisch unter http://127.0.0.1:8000

[Universal-Paket (Windows & Mac mit installiertem Python 3.10+)]
- Windows: Doppelklick auf "Start_OETSV_Tool.bat"
  (oder "Desktop-Icon-erstellen.vbs" für ein Desktop-Symbol).
- macOS:   Doppelklick auf "Start_OETSV_Tool.command".

------------------------------------------------------------------------
VEREIN EINSTELLEN & DATENSPEICHERUNG:
------------------------------------------------------------------------
- Öffne im Browser das Admin-Center: http://127.0.0.1:8000/adsi-admin
- Unter "Verein einstellen" kannst du deinen Vereinsnamen (z.B.
  "TSC Musterverein"), das Badge-Kürzel und dein IMAP-Postfach eintragen.
- ALLE DATEN BLEIBEN DAUERHAFT GESPEICHERT:
  * macOS App:   ~/Library/Application Support/pivitLABS-OETSV-Tool/
  * Windows App: %APPDATA%\\pivitLABS-OETSV-Tool\\
  * Universal:   Direkt im Unterordner data/adsi.db und .env
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
        # Add LIESMICH.txt and Windows Desktop Shortcut Creator
        zf.writestr(f"{root_folder}/LIESMICH.txt", LIESMICH_TEXT)
        zf.writestr(f"{root_folder}/Desktop-Icon-erstellen.vbs", WINDOWS_SHORTCUT_VBS)

        for rel in include_files:
            src = project_root / rel
            if src.exists():
                zf.write(src, f"{root_folder}/{rel}")

        # Add app/ directory (excluding __pycache__)
        app_dir = project_root / "app"
        for path in app_dir.rglob("*"):
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            if path.is_file():
                rel_path = path.relative_to(project_root)
                zf.write(path, f"{root_folder}/{rel_path.as_posix()}")

    return zip_path


def main() -> None:
    project_root = Path(__file__).resolve().parent
    release_dir = project_root / "release"
    release_dir.mkdir(exist_ok=True)

    # Keep PyInstaller cache inside build/ directory
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(project_root / "build" / ".pyinstaller_cache")

    # Write LIESMICH.txt to project root as well
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
        "--add-data", f"{project_root / 'app' / 'static'}{sep}app/static",
        "--add-data", f"{project_root / '.env.example'}{sep}.",
        "--collect-data", "tzdata",
        "--collect-data", "certifi",
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
    ]

    # On macOS create a native .app bundle (--windowed), on Windows show status console
    if sys.platform == "darwin":
        cmd.append("--windowed")
        cmd.extend(["--osx-bundle-identifier", "com.pivitlabs.oetsvtool"])
    else:
        cmd.append("--console")

    cmd.append(str(project_root / "launcher.py"))

    print("1/3 Baue eigenständige Desktop-App mit PyInstaller...")
    subprocess.check_call(cmd, cwd=str(project_root))

    print("2/3 Erstelle kundenfertige Installer-/Download-Pakete in release/...")
    dist_dir = project_root / "dist"

    if sys.platform == "darwin":
        app_bundle = dist_dir / "pivitLABS OETSV Tool.app"
        staging_dir = dist_dir / "pivitLABS-OETSV-Tool-macOS"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True)

        shutil.copytree(app_bundle, staging_dir / "pivitLABS OETSV Tool.app", symlinks=True)
        (staging_dir / "LIESMICH.txt").write_text(LIESMICH_TEXT, encoding="utf-8")

        # Create macOS ZIP using ditto (preserves macOS app permissions & symlinks)
        mac_zip = release_dir / "pivitLABS-OETSV-Tool-macOS.zip"
        if mac_zip.exists():
            mac_zip.unlink()
        subprocess.check_call(["ditto", "-c", "-k", "--keepParent", str(staging_dir), str(mac_zip)])

    elif sys.platform == "win32":
        win_app_dir = dist_dir / "pivitLABS OETSV Tool"
        (win_app_dir / "LIESMICH.txt").write_text(LIESMICH_TEXT, encoding="utf-8")
        (win_app_dir / "Desktop-Icon-erstellen.vbs").write_text(WINDOWS_SHORTCUT_VBS, encoding="utf-8")

        win_zip = release_dir / "pivitLABS-OETSV-Tool-Windows.zip"
        if win_zip.exists():
            win_zip.unlink()
        shutil.make_archive(
            str(release_dir / "pivitLABS-OETSV-Tool-Windows"),
            "zip",
            root_dir=str(dist_dir),
            base_dir="pivitLABS OETSV Tool"
        )

    print("3/3 Erstelle universelles PC & Mac Paket...")
    univ_zip = create_universal_zip(project_root, release_dir)

    print("\n" + "=" * 68)
    print("  FERTIG! Folgende Kunden-Pakete liegen bereit in: release/")
    print("=" * 68)
    for f in sorted(release_dir.iterdir()):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  -> {f.name:<45} ({size_mb:.1f} MB)")
    print("=" * 68)


if __name__ == "__main__":
    main()
