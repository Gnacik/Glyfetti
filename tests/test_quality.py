"""Font Quality Inspector regression coverage."""
import base64
import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
import pytest

from glyfetti.cli import main
from glyfetti.engine import FONTS_DIR
from glyfetti.quality import POLISH, inspect_atlas, inspect_style
from glyfetti.server import make_server


def small_style(chars="AąV"):
    return {
        "name": "quality_test",
        "font": str(FONTS_DIR / "TitanOne-Regular.ttf"),
        "size": 26,
        "supersample": 1,
        "chars": chars,
        "atlas_width": 256,
        "fill": {"stops": [[0, "#FFFFFF"], [1, "#FFD148"]]},
        "outline": {"color": "#442211", "width": 1},
        "preview": ["AąV"],
    }


def test_real_inspection_reads_rendered_atlas_and_metrics():
    report = inspect_style(small_style(), include_atlas=True)
    summary = report["summary"]
    assert report["atlas_png"].startswith("data:image/png;base64,iVBOR")
    assert summary["errors"] == 0
    assert summary["glyphs"] == 4  # three glyphs plus the standard space record
    assert summary["missing"] == 0
    assert len(report["polish"]) == len(POLISH)
    assert next(entry for entry in report["polish"] if entry["char"] == "ą")["status"] == "exported"
    assert next(entry for entry in report["polish"] if entry["char"] == "Ż")["status"] == "not_selected"
    for glyph in report["glyphs"]:
        assert glyph["codepoint"].startswith("U+")
    image = Image.open(io.BytesIO(base64.b64decode(report["atlas_png"].partition(",")[2])))
    assert list(image.size) == report["atlas"]


def test_missing_character_is_an_error_and_preserves_selected_coverage():
    style = small_style(chars="Aą😀")
    style["preview"] = ["Aą😀"]
    report = inspect_style(style)
    assert "atlas_png" not in report
    assert report["summary"]["missing"] == 1
    assert any(issue["code"] == "missing" and issue["char"] == "😀" for issue in report["issues"])


def test_corrupt_metrics_detect_bounds_overlap_empty_and_clipping():
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    image.putpixel((1, 1), (255, 255, 255, 255))
    metadata = {
        "name": "damaged", "size": 12, "scaleW": 32, "scaleH": 32,
        "baseline": 10, "lineHeight": 14,
        "chars": [
            {"id": 32, "x": 0, "y": 0, "w": 0, "h": 0, "xo": 0, "yo": 0, "xa": 5},
            {"id": 65, "x": 1, "y": 1, "w": 10, "h": 10, "xo": 0, "yo": 1, "xa": 10},
            {"id": 66, "x": 5, "y": 5, "w": 10, "h": 10, "xo": 0, "yo": 1, "xa": 10},
            {"id": 67, "x": 30, "y": 3, "w": 10, "h": 6, "xo": 0, "yo": 0, "xa": 12},
        ],
        "kernings": [{"first": 65, "second": 88, "amount": -4}],
    }
    report = inspect_atlas(image, metadata, requested="ABCD", clipped=["A"])
    codes = {issue["code"] for issue in report["issues"]}
    assert {"transparent", "overlap", "bounds", "missing", "clipped", "kerning_reference"} <= codes
    assert report["summary"]["errors"] >= 6
    assert any(glyph["char"] == "A" and "clipped" in glyph["issues"] for glyph in report["glyphs"])


def test_cli_saves_report_and_strict_mode_detects_errors(tmp_path, capsys):
    source = tmp_path / "font.json"
    source.write_text(json.dumps(small_style()), "utf-8")
    out = tmp_path / "quality.json"
    assert main(["inspect", str(source), "-o", str(out), "--strict"]) == 0
    report = json.loads(out.read_text("utf-8"))
    assert report["summary"]["errors"] == 0
    assert not (tmp_path / "out").exists()
    assert "glyphs" in capsys.readouterr().out

    broken = small_style(chars="A😀")
    broken["preview"] = ["A😀"]
    source.write_text(json.dumps(broken), "utf-8")
    assert main(["inspect", str(source), "--strict"]) == 1


def test_editor_inspect_endpoint_is_authenticated_and_returns_png():
    with make_server(0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = "http://127.0.0.1:" + str(server.server_port)
        try:
            with urlopen(url + "/api/catalog") as response:
                token = json.load(response)["token"]
            data = json.dumps(small_style()).encode()
            req = Request(url + "/api/inspect", data=data,
                          headers={"X-Glyfetti-Token": token, "Content-Type": "application/json"})
            with urlopen(req) as response:
                report = json.load(response)
            assert report["summary"]["glyphs"] == 4
            assert report["atlas_png"].startswith("data:image/png;base64,")
            with pytest.raises(HTTPError) as rejected:
                urlopen(Request(url + "/api/inspect", data=data))
            assert rejected.value.code == 403
        finally:
            server.shutdown()
            worker.join(timeout=5)
