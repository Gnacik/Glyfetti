"""Font Quality Inspector: checks actual rendered atlas pixels and exported metrics.

Warnings are diagnostics, not guesses about typographic aesthetics. Inspecting a
style never writes into its source directory or modifies its JSON/font files.
"""
import base64
import json
from pathlib import Path
import tempfile

from PIL import Image

from .engine import build, prepare_style

POLISH = "ĄĆĘŁŃÓŚŹŻąćęłńóśźż"


def inspect_atlas(atlas, metadata, requested="", clipped=()):
    """Inspect an atlas+metrics pair (also useful for external corrupted fixtures).

    Returns JSON-serializable diagnostics. A non-exported Polish glyph is shown as
    "not selected", not falsely reported as a missing glyph.
    """
    width, height = atlas.size
    issues = []
    glyphs = []
    seen = set()
    rendered = set()
    rectangles = []
    alpha_channel = atlas.getchannel('A')

    def issue(code, severity, message, char=None):
        item = {"code": code, "severity": severity, "message": message}
        if char is not None:
            item["char"] = char
        issues.append(item)
        return code

    if (metadata.get("scaleW"), metadata.get("scaleH")) != (width, height):
        issue("atlas_dimensions", "error", "Atlas image dimensions differ from JSON metrics.")
    baseline = metadata.get("baseline", 0)
    line_height = metadata.get("lineHeight", 0)
    if not isinstance(baseline, int) or not isinstance(line_height, int) or baseline < 0 or line_height <= 0 or baseline > line_height:
        issue("line_metrics", "error", "Baseline or line-height metrics are inconsistent.")

    for raw in metadata.get("chars", []):
        cp = raw.get("id")
        if not isinstance(cp, int) or not 0 <= cp <= 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
            issue("codepoint", "error", "Invalid Unicode code point in font metadata.")
            continue
        ch = chr(cp)
        row = {
            "char": ch, "id": cp, "codepoint": f"U+{cp:04X}",
            "x": raw.get("x"), "y": raw.get("y"),
            "w": raw.get("w"), "h": raw.get("h"),
            "xo": raw.get("xo"), "yo": raw.get("yo"), "xa": raw.get("xa"),
            "issues": [],
        }
        glyphs.append(row)
        def mark(code, severity, message):
            row["issues"].append(code)
            issue(code, severity, message, ch)

        if cp in seen:
            mark("duplicate", "error", "Duplicate glyph code point.")
        seen.add(cp)
        coords = [row[k] for k in ("x", "y", "w", "h", "xo", "yo", "xa")]
        if not all(isinstance(value, int) for value in coords):
            mark("metrics_type", "error", "Glyph metrics must be integers.")
            continue
        x, y, w, h, xo, yo, adv = coords
        if adv <= 0 and not ch.isspace():
            mark("advance", "warning", "Non-positive character advance; text may overlap.")
        if cp == 32:  # Intentional zero-sized space in the exported format.
            if w or h:
                mark("space_bounds", "warning", "Space has a visible glyph rectangle.")
            rendered.add(cp)
            continue
        if w <= 0 or h <= 0:
            mark("empty", "error", "Glyph rectangle is empty.")
            continue
        if x < 0 or y < 0 or x + w > width or y + h > height:
            mark("bounds", "error", "Glyph rectangle extends beyond atlas texture.")
            continue
        rendered.add(cp)
        rectangles.append((x, y, x + w, y + h, row))
        alpha = alpha_channel.crop((x, y, x + w, y + h))
        if alpha.getbbox() is None:
            mark("transparent", "error", "Atlas rectangle contains no visible pixels.")
        if abs(xo) > max(64, metadata.get("size", 32) * 2) or abs(yo) > max(64, metadata.get("size", 32) * 2):
            mark("offset", "warning", "Unusually large glyph offset; check the baseline.")
        # Expected overhangs for outlines are normal. Only flag extreme extremes.
        if xo + w - adv > max(16, metadata.get("size", 32) * .8):
            mark("overhang", "warning", "Glyph extends far beyond its horizontal advance.")

    rectangles.sort(key=lambda item: item[0])
    for i, (x1, y1, x2, y2, row) in enumerate(rectangles):
        for ax1, ay1, ax2, ay2, other in rectangles[i + 1:]:
            if ax1 >= x2:
                break
            if y1 < ay2 and ay1 < y2:
                if "overlap" not in row["issues"]:
                    row["issues"].append("overlap")
                if "overlap" not in other["issues"]:
                    other["issues"].append("overlap")
                issue("overlap", "error", f"Atlas glyph rectangles overlap ({row['codepoint']} and {other['codepoint']}).", row["char"])

    for ch in sorted(set(clipped)):
        match = next((row for row in glyphs if row["char"] == ch), None)
        if match:
            match["issues"].append("clipped")
        issue("clipped", "error", "Effects touch the pre-crop render buffer edge; artwork may be clipped.", ch)

    requested_codes = {ord(ch) for ch in requested if ch == " " or not ch.isspace()}
    for cp in sorted(requested_codes - rendered):
        if 0 <= cp <= 0x10FFFF:
            issue("missing", "error", "Requested character is missing from the exported atlas.", chr(cp))

    for pair in metadata.get("kernings", []):
        left, right, value = pair.get("first"), pair.get("second"), pair.get("amount")
        if left not in seen or right not in seen or not isinstance(value, int):
            issue("kerning_reference", "error", "Kerning pair refers to a missing glyph or has invalid adjustment.")
        elif abs(value) > max(8, metadata.get("size", 32) * .5):
            issue("kerning_outlier", "warning", f"Large kerning adjustment: {value} px.", chr(left) + chr(right))

    polish = []
    for ch in POLISH:
        selected = ch in requested
        exported = ord(ch) in rendered
        polish.append({"char": ch, "selected": selected, "exported": exported,
                       "status": "exported" if exported else ("missing" if selected else "not_selected")})

    return {
        "name": metadata.get("name", "font"),
        "atlas": [width, height],
        "metrics": {"size": metadata.get("size"), "baseline": baseline, "line_height": line_height},
        "summary": {
            "glyphs": len(glyphs),
            "errors": sum(x["severity"] == "error" for x in issues),
            "warnings": sum(x["severity"] == "warning" for x in issues),
            "missing": sum(x["code"] == "missing" for x in issues),
            "clipped": sum(x["code"] == "clipped" for x in issues),
            "kerning_pairs": len(metadata.get("kernings", [])),
        },
        "glyphs": glyphs,
        "polish": polish,
        "issues": issues,
        "kerning": metadata.get("kernings", []),
    }


def inspect_style(style, base=".", include_atlas=False):
    """Build real full-quality atlas in a temporary directory and inspect it."""
    raw = prepare_style(style, base)
    with tempfile.TemporaryDirectory(prefix="glyfetti-inspect-") as directory:
        root = Path(directory)
        input_file = root / "style.json"
        input_file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        output = root / "out"
        result = build(input_file, out_dir=output, inspect=True)
        metadata = json.loads((output / (result["name"] + ".json")).read_text("utf-8"))
        with Image.open(output / (result["name"] + ".png")) as image:
            report = inspect_atlas(image, metadata, raw["chars"], result["clipped_glyphs"])
        report["summary"]["occupancy"] = round(result["occupancy"], 4)
        report["summary"]["packing"] = result["packing"]
        if include_atlas:
            atlas_bytes = (output / (result["name"] + ".png")).read_bytes()
            report["atlas_png"] = "data:image/png;base64," + base64.b64encode(atlas_bytes).decode("ascii")
        return report
