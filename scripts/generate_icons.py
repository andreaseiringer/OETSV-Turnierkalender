#!/usr/bin/env python3
"""
Generate square PWA icons (192x192, 512x512, apple-touch-icon 180x180)
and OS installer icons (.ico for Windows, .icns for macOS) from pivitlabs-logo.png.
"""
import subprocess
import shutil
from pathlib import Path
from PIL import Image


def create_square_icon(src_logo: Path, size: int, bg_color=(15, 23, 42, 255)) -> Image.Image:
    logo = Image.open(src_logo).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), bg_color)
    # Fit logo within 82% of canvas width
    max_w = int(size * 0.82)
    max_h = int(size * 0.82)
    ratio = min(max_w / logo.width, max_h / logo.height)
    new_w = max(1, int(logo.width * ratio))
    new_h = max(1, int(logo.height * ratio))
    resized = logo.resize((new_w, new_h), Image.Resampling.LANCZOS)
    offset_x = (size - new_w) // 2
    offset_y = (size - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y), resized)
    return canvas


def generate_all_icons(project_root: Path) -> None:
    img_dir = project_root / "app" / "static" / "img"
    src_logo = img_dir / "pivitlabs-logo.png"
    if not src_logo.exists():
        raise FileNotFoundError(f"Logo nicht gefunden: {src_logo}")

    # 1. PWA & Touch Icons
    for size, filename in [
        (192, "icon-192.png"),
        (512, "icon-512.png"),
        (180, "apple-touch-icon.png"),
        (64, "favicon.png"),
    ]:
        icon = create_square_icon(src_logo, size)
        icon.save(img_dir / filename, format="PNG")

    # 2. Windows .ico (multi-size)
    ico_base = create_square_icon(src_logo, 256)
    ico_path = img_dir / "app-icon.ico"
    ico_base.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    # 3. macOS .icns
    icns_path = img_dir / "app-icon.icns"
    iconset_dir = project_root / "build" / "AppIcon.iconset"
    if shutil.which("iconutil"):
        if iconset_dir.exists():
            shutil.rmtree(iconset_dir)
        iconset_dir.mkdir(parents=True, exist_ok=True)
        mac_sizes = [
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ]
        for sz, name in mac_sizes:
            create_square_icon(src_logo, sz).save(iconset_dir / name, format="PNG")
        subprocess.check_call(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)])
        shutil.rmtree(iconset_dir, ignore_errors=True)
    else:
        # Fallback via Pillow ICNS support on non-macOS hosts
        try:
            create_square_icon(src_logo, 512).save(icns_path, format="ICNS")
        except Exception:
            pass


if __name__ == "__main__":
    generate_all_icons(Path(__file__).resolve().parent.parent)
    print("Alle PWA- und Desktop-App-Icons erfolgreich generiert.")
