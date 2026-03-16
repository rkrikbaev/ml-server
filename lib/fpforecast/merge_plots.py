import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge all .png files under a directory into a single PDF."
    )
    parser.add_argument(
        "root_dir",
        type=str,
        help="Root directory to search for .png files.",
    )
    parser.add_argument(
        "output_pdf",
        type=str,
        help="Output PDF file path.",
    )
    return parser.parse_args()


def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    """
    Pillow 10+ removed draw.textsize, so we use textbbox when available
    and fall back to textsize for older versions.
    """
    if hasattr(draw, "textbbox"):
        # Pillow >= 8.0, recommended way
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return right - left, bottom - top
    else:
        # Older Pillow versions
        return draw.textsize(text, font=font)


def pngs_to_pdf(
    root_dir: str,
    output_pdf: str,
    margin: int = 10,
    bg_color: str = "white",
    text_color: str = "black",
):
    root_dir = Path(root_dir)
    png_files = sorted(root_dir.rglob("*.png"))
    if not png_files:
        raise ValueError(f"No .png files found under {root_dir}")

    # Use default bitmap font; replace with truetype if you want:
    # font = ImageFont.truetype("/path/to/font.ttf", font_size)
    font = ImageFont.load_default()

    pages = []

    for path in png_files:
        rel_path = path.relative_to(root_dir)
        img = Image.open(path)

        # PDF doesn't like alpha channels
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        text = str(rel_path)

        # Measure text size using helper
        # (we can use a tiny dummy image just for measurement)
        dummy = Image.new("RGB", (1, 1))
        tmp_draw = ImageDraw.Draw(dummy)
        text_width, text_height = measure_text(tmp_draw, text, font)

        # New canvas: original image + strip for text at the bottom
        canvas_width = max(img.width, text_width + 2 * margin)
        canvas_height = img.height + text_height + 2 * margin

        canvas = Image.new("RGB", (canvas_width, canvas_height), bg_color)

        # Paste the image at the top-left
        canvas.paste(img, (0, 0))

        # Draw text in the bottom strip
        draw = ImageDraw.Draw(canvas)
        text_x = margin
        text_y = img.height + margin
        draw.text((text_x, text_y), text, fill=text_color, font=font)

        pages.append(canvas)

    first, *rest = pages
    first.save(output_pdf, save_all=True, append_images=rest)

    print(f"Saved {len(pages)} pages to {output_pdf}")


def main(args):
    pngs_to_pdf(args.root_dir, args.output_pdf)


if __name__ == "__main__":
    args = parse_args()
    main(args)
