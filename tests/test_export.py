import json
from pathlib import Path
import shutil

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageFont
import pytest

from glyfetti.cli import main
from glyfetti.engine import build, effect_padding, FONTS_DIR, render_glyph, resolve_font, shelf_pack, style_glyph
from glyfetti.patch import patch_font
from glyfetti.validation import validate_style


@pytest.fixture
def style():
    return {'name': 'test', 'font': str(FONTS_DIR / 'TitanOne-Regular.ttf'),
            'size': 24, 'supersample': 1, 'chars': 'AVą', 'atlas_width': 256,
            'fill': {'stops': [[0, '#ffffff'], [1, '#ffcc00']]},
            'outline': {'color': '#000000', 'width': 1}, 'preview': ['AVą']}


@pytest.mark.parametrize('change,field', [
    ({'atlas_width': 0}, 'atlas_width'), ({'size': 12.5}, 'size'),
    ({'name': '../escape'}, 'name'), ({'preview': []}, 'preview'),
    ({'shadow': {'blur': 2}}, 'shadow'),
    ({'fill': {'stops': [[1, '#ffffff'], [0, '#000000']]}}, 'fill.stops'),
    ({'tracking': float('nan')}, 'tracking'),
])
def test_invalid_styles_fail_before_render(style, change, field):
    style.update(change)
    with pytest.raises(ValueError, match=field):
        validate_style(style)


def test_disabled_effect_needs_no_parameters(style):
    style['shadow'] = {'enabled': False}
    validate_style(style)


def test_packing_refuses_cropped_glyphs_and_oversized_textures():
    with pytest.raises(ValueError, match='glyph width'):
        shelf_pack([(100, 20)], 32, 2)
    with pytest.raises(ValueError, match='atlas height'):
        shelf_pack([(20, 40)] * 10, 32, 2, max_height=64)


def test_export_metrics_stay_inside_texture(style, tmp_path):
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(style), 'utf-8')
    build(source, tmp_path / 'out')
    metadata = json.loads((tmp_path / 'out/test.json').read_text())
    with Image.open(tmp_path / 'out/test.png') as image:
        assert image.size == (metadata['scaleW'], metadata['scaleH'])
        for char in metadata['chars']:
            assert 0 <= char['x'] <= char['x'] + char['w'] <= image.width
            assert 0 <= char['y'] <= char['y'] + char['h'] <= image.height
        assert image.mode == 'RGBA'
    bmfont = (tmp_path / 'out/test.fnt').read_text()
    assert f"chars count={len(metadata['chars'])}" in bmfont
    for char in metadata['chars']:
        assert f"char id={char['id']} " in bmfont


def test_effect_padding_preserves_long_side_and_negative_shadow(style):
    style['side'] = {'depth': 35, 'dx': -30, 'color_top': '#ffcc00', 'color_bottom': '#885500'}
    style['shadow'] = {'dx': -40, 'dy': -30, 'blur': 3, 'color': '#000000', 'opacity': 1}
    font = ImageFont.truetype(style['font'], style['size'])
    pad = effect_padding(style, font, 'A', 1)
    mask, _, _ = render_glyph('A', font, 1, pad)
    alpha = style_glyph(mask, style, 1)[..., 3]
    assert alpha[0].max() < 1 / 255
    assert alpha[-1].max() < 1 / 255
    assert alpha[:, 0].max() < 1 / 255
    assert alpha[:, -1].max() < 1 / 255


def test_patch_cache_distinguishes_fonts_with_same_filename(style, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'home')
    results = []
    for index, name in enumerate(('Chewy-Regular.ttf', 'Sniglet-ExtraBold.ttf')):
        directory = tmp_path / str(index)
        directory.mkdir()
        path = directory / 'same.ttf'
        shutil.copyfile(FONTS_DIR / name, path)
        custom = dict(style, font=str(path), chars='ą')
        patched, _ = resolve_font(custom, tmp_path)
        results.append(patched)
        with TTFont(patched) as font:
            assert ord('ą') in font.getBestCmap()
    assert results[0] != results[1]


def test_patch_without_reference_accents_or_base_characters(tmp_path):
    source = tmp_path / 'small.ttf'
    with TTFont(FONTS_DIR / 'Chewy-Regular.ttf') as font:
        for table in font['cmap'].tables:
            if table.isUnicode():
                for char in 'ÓóNn':
                    table.cmap.pop(ord(char), None)
        font.save(source)
    added = patch_font(source, tmp_path / 'patched.ttf')
    assert 'ą' in added
    assert 'ń' not in added


def test_cff_font_with_missing_diacritics_still_builds(style, tmp_path):
    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder(['.notdef', 'A'])
    builder.setupCharacterMap({65: 'A'})
    builder.setupHorizontalMetrics({'.notdef': (600, 0), 'A': (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': 'TestCFF', 'styleName': 'Regular'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    pen = T2CharStringPen(600, None)
    pen.moveTo((50, 0)); pen.lineTo((300, 700)); pen.lineTo((550, 0)); pen.closePath()
    charstring = pen.getCharString()
    builder.setupCFF('TestCFF', {}, {'.notdef': charstring, 'A': charstring}, {})
    font_path = tmp_path / 'font.otf'
    builder.save(font_path)
    style.update(font=str(font_path), chars='Aą', preview=['Aą'])
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(style), 'utf-8')
    with pytest.warns(UserWarning, match='CFF'):
        result = build(source, tmp_path / 'out')
    assert result['skipped'] == 'ą'
    assert result['glyphs'] == 1


def test_cli_reports_invalid_style_without_traceback(style, tmp_path, capsys):
    style['size'] = 0
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(style), 'utf-8')
    assert main(['build', str(path)]) == 2
    assert 'size:' in capsys.readouterr().err
    assert not (tmp_path / 'out').exists()


def test_preview_keeps_large_negative_shadow_and_negative_advances(style, tmp_path):
    style.update(tracking=-50, preview=['AAA'], preview_bg='transparent')
    style['shadow'] = {'dx': -100, 'dy': -80, 'blur': 0, 'opacity': 1, 'color': '#000000'}
    path = tmp_path / 'style.json'
    path.write_text(json.dumps(style), 'utf-8')
    build(path, tmp_path / 'out')
    with Image.open(tmp_path / 'out/test_preview.png') as preview:
        left, top, right, bottom = preview.getbbox()
        assert left >= 40 and top >= 30
        assert right <= preview.width - 40 and bottom <= preview.height - 30


def test_gallery_supports_transparency_without_writing_into_presets(style, tmp_path):
    from glyfetti.gallery import make_gallery
    presets = tmp_path / 'presets'
    presets.mkdir()
    style['preview_bg'] = 'transparent'
    (presets / 'example.json').write_text(json.dumps(style), 'utf-8')
    output = tmp_path / 'gallery.png'
    make_gallery(presets, output)
    assert output.is_file()
    assert not (presets / 'out').exists()
