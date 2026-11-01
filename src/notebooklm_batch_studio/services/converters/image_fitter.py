"""Fit a NotebookLM infographic onto device-sized canvases without cropping.

NotebookLM only lets us pick landscape / portrait / square, not an exact size, so the image is
scaled to fit inside each target canvas and centered on a white background (letterboxing).
Nothing is cropped, so every part of the infographic stays readable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

A4_DPI = 300


@dataclass(frozen=True)
class DeviceTarget:
    """One output canvas.

    Attributes:
        suffix: File name suffix, e.g. 'A4'.
        width: Canvas width in pixels.
        height: Canvas height in pixels.
        extension: Output extension ('.pdf' or '.png').
    """

    suffix: str
    width: int
    height: int
    extension: str


DEVICE_TARGETS: tuple[DeviceTarget, ...] = (
    DeviceTarget("A4", 2480, 3508, ".pdf"),  # 210 x 297 mm at 300 dpi, portrait
    DeviceTarget("iPadAir4", 1640, 2360, ".png"),  # iPad Air 4 native, portrait
    DeviceTarget("MacBookPro14", 3024, 1964, ".png"),  # MacBook Pro 14" native, landscape
)


def fit_on_canvas(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale an image to fit inside a canvas and center it on white, keeping its aspect ratio.

    Args:
        image: Source image.
        width: Canvas width in pixels.
        height: Canvas height in pixels.

    Returns:
        New RGB image of exactly width x height.
    """
    source = image.convert("RGB")
    scale = min(width / source.width, height / source.height)
    size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
    resized = source.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(resized, ((width - size[0]) // 2, (height - size[1]) // 2))
    return canvas


def export_device_versions(source_png: Path) -> list[Path]:
    """Write A4 PDF, iPad Air 4 and MacBook Pro 14 versions next to an infographic.

    Args:
        source_png: Downloaded infographic image (e.g. infographic.png).

    Returns:
        Paths of the files written, e.g. infographic_A4.pdf, infographic_iPadAir4.png.
    """
    written: list[Path] = []
    with Image.open(source_png) as image:
        for target in DEVICE_TARGETS:
            out = source_png.with_name(f"{source_png.stem}_{target.suffix}{target.extension}")
            fitted = fit_on_canvas(image, target.width, target.height)
            if target.extension == ".pdf":
                fitted.save(out, "PDF", resolution=A4_DPI)
            else:
                fitted.save(out, "PNG")
            written.append(out)
    logger.info("Exported %d device versions of %s", len(written), source_png.name)
    return written
