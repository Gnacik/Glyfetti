import json
from pathlib import Path

from PIL import Image

from glyfetti.engine import build

ROOT = Path(__file__).resolve().parents[1]
PRESETS = sorted((ROOT / "presets").glob("*.json"))


def test_presets_validate_against_schema():
    jsonschema = __import__("pytest").importorskip("jsonschema")
    schema = json.loads((ROOT / "schema" / "style.schema.json").read_text("utf-8"))
    for p in PRESETS:
        jsonschema.validate(json.loads(p.read_text("utf-8")), schema)


def test_every_preset_renders_preview(tmp_path):
    for p in PRESETS:
        r = build(p, out_dir=tmp_path, preview_only=True)
        assert r["glyphs"] > 0
        assert (tmp_path / f"{r['name']}_preview.png").exists()


def test_polish_characters_present_after_build(tmp_path):
    style = json.loads((ROOT / "presets" / "chocolate_cream.json").read_text("utf-8"))
    style["chars"] = "AaĄąĘęŻż"
    style["font"] = str((ROOT / "presets" / style["font"]).resolve())
    f = tmp_path / "pl.json"
    f.write_text(json.dumps(style, ensure_ascii=False), "utf-8")
    r = build(f, out_dir=tmp_path)
    assert r["skipped"] == ""
    meta = json.loads((tmp_path / f"{r['name']}.json").read_text("utf-8"))
    ids = {c["id"] for c in meta["chars"]}
    assert all(ord(c) in ids for c in "ĄąĘęŻż")
    assert Image.open(tmp_path / f"{r['name']}.png").mode == "RGBA"


def test_parallel_build_matches_sequential(tmp_path):
    preset = ROOT / "presets" / "fire.json"
    build(preset, out_dir=tmp_path / "seq", preview_only=True, workers=1)
    build(preset, out_dir=tmp_path / "par", preview_only=True, workers=4)
    for ext in ("png", "fnt", "json"):
        assert (tmp_path / "seq" / f"fire.{ext}").read_bytes() == (tmp_path / "par" / f"fire.{ext}").read_bytes()
