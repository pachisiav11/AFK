"""Generate AFK app icons from the project logo source.

Produces assets/icon.png, assets/tray.png, and assets/icon.ico used by
Electron and electron-builder.

Run: python/.venv/Scripts/python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SOURCE = ASSETS / "logo-source.png"


def _fit_square(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA")
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fitted = img.resize((size, size), Image.Resampling.LANCZOS)
    canvas.alpha_composite(fitted, (0, 0))
    return canvas


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Logo source not found: {SOURCE}")

    ASSETS.mkdir(exist_ok=True)
    source = Image.open(SOURCE)
    app = _fit_square(source, 512)
    tray = _fit_square(source, 64)

    app.save(ASSETS / "icon.png")
    tray.save(ASSETS / "tray.png")
    app.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("Wrote icon.png, tray.png, icon.ico to", ASSETS)


if __name__ == "__main__":
    main()
