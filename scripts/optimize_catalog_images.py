#!/usr/bin/env python3
"""Create adjacent WebP versions of catalog PNG and JPEG images."""

from __future__ import annotations

import argparse
import io
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_DIMENSION = 2000
WEBP_QUALITY = 82
DEFAULT_DIRECTORIES = ("catalog/catalog", "gallery")


def find_images(root: Path, directories: list[str]) -> list[Path]:
    images: set[Path] = set()
    for directory in directories:
        folder = (root / directory).resolve()
        try:
            folder.relative_to(root)
        except ValueError as error:
            raise ValueError(f"Image directory must be inside the repository: {directory}") from error
        if not folder.exists():
            continue
        if folder.is_file():
            if folder.suffix.lower() in SUPPORTED_EXTENSIONS:
                images.add(folder)
            continue
        if not folder.is_dir():
            raise NotADirectoryError(f"Image directory does not exist as a directory: {folder}")
        images.update(
            image
            for image in folder.rglob("*")
            if image.is_file() and image.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    return sorted(images)


def optimized_bytes(source: Path) -> bytes:
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original)
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        image = image.convert("RGBA" if has_alpha else "RGB")

        width, height = image.size
        if max(width, height) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(width, height)
            dimensions = (max(1, round(width * scale)), max(1, round(height * scale)))
            image = image.resize(dimensions, Image.Resampling.LANCZOS)

        options = {"format": "WEBP", "quality": WEBP_QUALITY, "method": 6}
        if has_alpha:
            options["alpha_quality"] = 100
        icc_profile = original.info.get("icc_profile")
        if icc_profile:
            options["icc_profile"] = icc_profile

        output = io.BytesIO()
        image.save(output, **options)
        return output.getvalue()


def write_if_changed(destination: Path, content: bytes) -> bool:
    if destination.exists() and destination.read_bytes() == content:
        return False

    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (defaults to the repository containing this script)",
    )
    parser.add_argument(
        "directories",
        nargs="*",
        help=f"Image directories relative to --root (defaults to: {', '.join(DEFAULT_DIRECTORIES)})",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    directories = args.directories or [
        directory for directory in DEFAULT_DIRECTORIES if (root / directory).is_dir()
    ]
    if not directories:
        parser.error("No catalog image directories found; provide one or more directories")

    sources = find_images(root, directories)
    changed = 0
    for source in sources:
        destination = source.with_suffix(".webp")
        if write_if_changed(destination, optimized_bytes(source)):
            changed += 1
            print(f"Optimized {source.relative_to(root)} -> {destination.relative_to(root)}")
        else:
            print(f"Unchanged {destination.relative_to(root)}")

    print(f"Processed {len(sources)} source image(s); updated {changed} WebP file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
