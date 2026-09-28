#!/usr/bin/env python3
"""Create labeled contact sheets and an HTML gallery for V5 asset stills."""

from __future__ import annotations

import argparse
import html
import json
import math
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SCENE_ORDER = ["the_shed", "hidden_alley", "italian_flat", "pine_forest"]
SCENE_LABELS = {
    "the_shed": "The Shed",
    "hidden_alley": "Hidden Alley",
    "italian_flat": "Italian Flat",
    "pine_forest": "Pine Forest",
}


def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def fit_image(image: Image.Image, width: int, height: int) -> Image.Image:
    result = image.copy().convert("RGB")
    result.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), (24, 27, 32))
    canvas.paste(result, ((width - result.width) // 2, (height - result.height) // 2))
    return canvas


def compose_objects(root: Path, output: Path) -> list[Path]:
    manifest_path = root / "objects" / "render_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = sorted(manifest["rendered"], key=lambda row: ((row.get("category") or ""), row["name"]))
    output.mkdir(parents=True, exist_ok=True)
    columns, rows_per_page = 4, 3
    tile_width, image_height, label_height = 480, 360, 86
    per_page = columns * rows_per_page
    title_font = font(22)
    meta_font = font(17)
    pages = []
    for page_index in range(math.ceil(len(rows) / per_page)):
        subset = rows[page_index * per_page : (page_index + 1) * per_page]
        page = Image.new(
            "RGB",
            (columns * tile_width, rows_per_page * (image_height + label_height)),
            (15, 17, 21),
        )
        draw = ImageDraw.Draw(page)
        for offset, row in enumerate(subset):
            global_index = page_index * per_page + offset + 1
            x = (offset % columns) * tile_width
            y = (offset // columns) * (image_height + label_height)
            source = root.parent.parent / row["output"]
            thumb = fit_image(Image.open(source), tile_width, image_height)
            page.paste(thumb, (x, y))
            draw.rectangle((x, y + image_height, x + tile_width, y + image_height + label_height), fill=(29, 33, 40))
            name_lines = textwrap.wrap(row["name"], width=38)[:2]
            draw.text((x + 12, y + image_height + 7), f"{global_index:02d}  {name_lines[0]}", fill=(245, 245, 245), font=title_font)
            if len(name_lines) > 1:
                draw.text((x + 50, y + image_height + 33), name_lines[1], fill=(245, 245, 245), font=title_font)
            category_y = y + image_height + (59 if len(name_lines) > 1 else 38)
            draw.text((x + 12, category_y), row.get("category") or "Uncategorized", fill=(164, 181, 205), font=meta_font)
        page_path = output / f"objects_{page_index + 1:02d}.jpg"
        page.save(page_path, quality=92, subsampling=0)
        pages.append(page_path)
    return pages


def build_scene_manifest(root: Path) -> dict:
    scene_root = root / "scenes"
    reports = {}
    for path in scene_root.glob("*.json"):
        if path.name == "render_manifest.json":
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        if "tag" in row and "output" in row:
            reports[row["tag"]] = row
    rendered = [reports[tag] for tag in SCENE_ORDER if tag in reports]
    manifest = {
        "scope": "previously untested official scene candidates",
        "rendered_count": len(rendered),
        "rendered": rendered,
    }
    (scene_root / "render_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def compose_scenes(root: Path, output: Path, scene_rows: list[dict]) -> Path | None:
    if not scene_rows:
        return None
    output.mkdir(parents=True, exist_ok=True)
    tile_width, image_height, label_height = 960, 540, 84
    page = Image.new("RGB", (tile_width * 2, (image_height + label_height) * 2), (15, 17, 21))
    draw = ImageDraw.Draw(page)
    title_font = font(26)
    meta_font = font(17)
    for index, row in enumerate(scene_rows[:4]):
        x = (index % 2) * tile_width
        y = (index // 2) * (image_height + label_height)
        source = root.parent.parent / row["output"]
        page.paste(fit_image(Image.open(source), tile_width, image_height), (x, y))
        draw.rectangle((x, y + image_height, x + tile_width, y + image_height + label_height), fill=(29, 33, 40))
        label = SCENE_LABELS.get(row["tag"], row["tag"])
        camera = row.get("camera", {}).get("name", "author camera")
        samples = row.get("render", {}).get("samples", "?")
        composite = row.get("content_policy", {}).get("author_compositing_enabled", True)
        composite_note = "author composite" if composite else "author composite disabled"
        draw.text((x + 14, y + image_height + 7), f"{index + 1}. {label}", fill=(245, 245, 245), font=title_font)
        draw.text((x + 14, y + image_height + 38), f"camera: {camera}", fill=(164, 181, 205), font=meta_font)
        draw.text((x + 14, y + image_height + 60), f"{samples} samples; {composite_note}", fill=(164, 181, 205), font=meta_font)
    path = output / "scenes_01.jpg"
    page.save(path, quality=94, subsampling=0)
    return path


def write_gallery(root: Path, output: Path) -> Path:
    object_manifest = json.loads((root / "objects" / "render_manifest.json").read_text(encoding="utf-8"))
    object_rows = sorted(object_manifest["rendered"], key=lambda row: ((row.get("category") or ""), row["name"]))
    scene_manifest_path = root / "scenes" / "render_manifest.json"
    scene_rows = []
    if scene_manifest_path.is_file():
        scene_rows = json.loads(scene_manifest_path.read_text(encoding="utf-8")).get("rendered", [])

    cards = []
    for index, row in enumerate(object_rows, start=1):
        relative = Path("objects") / Path(row["output"]).name
        cards.append(
            f'<figure><a href="{html.escape(relative.as_posix())}"><img src="{html.escape(relative.as_posix())}" loading="lazy"></a>'
            f'<figcaption>{index:02d}. {html.escape(row["name"])}<br><small>{html.escape(row.get("category") or "Uncategorized")}</small></figcaption></figure>'
        )
    scene_cards = []
    for row in scene_rows:
        relative = Path("scenes") / Path(row["output"]).name
        label = SCENE_LABELS.get(row["tag"], row["tag"])
        camera = row.get("camera", {}).get("name", "author camera")
        missing = len(row.get("missing_images", []))
        samples = row.get("render", {}).get("samples", "?")
        composite = row.get("content_policy", {}).get("author_compositing_enabled", True)
        composite_note = "author composite" if composite else "author composite disabled"
        scene_cards.append(
            f'<figure><a href="{html.escape(relative.as_posix())}"><img src="{html.escape(relative.as_posix())}"></a>'
            f'<figcaption>{html.escape(label)}<br><small>camera: {html.escape(camera)}; {samples} samples; '
            f'{html.escape(composite_note)}; missing images: {missing}</small></figcaption></figure>'
        )
    content = f"""<!doctype html>
<meta charset="utf-8">
<title>V5 Asset Realism Review</title>
<style>
body{{background:#11151a;color:#edf1f5;font:16px system-ui;margin:24px}}h1,h2{{font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px}}
figure{{margin:0;background:#1c222a;border:1px solid #303946;border-radius:8px;overflow:hidden}}
img{{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;background:#222}}
figcaption{{padding:10px 12px;overflow-wrap:anywhere}}small{{color:#a9bad0}}
</style>
<h1>V5 Asset Realism Review</h1>
<h2>Scenes ({len(scene_rows)})</h2><div class="grid">{''.join(scene_cards)}</div>
<h2>Untested rigid objects ({len(object_rows)})</h2><div class="grid">{''.join(cards)}</div>
"""
    output.mkdir(parents=True, exist_ok=True)
    path = root / "index.html"
    path.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    scene_manifest = build_scene_manifest(root)
    sheets = compose_objects(root, root / "contact_sheets")
    scene_sheet = compose_scenes(root, root / "contact_sheets", scene_manifest["rendered"])
    gallery = write_gallery(root, root)
    print(
        json.dumps(
            {
                "object_contact_sheets": [str(path) for path in sheets],
                "scene_contact_sheet": str(scene_sheet) if scene_sheet else None,
                "gallery": str(gallery),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
