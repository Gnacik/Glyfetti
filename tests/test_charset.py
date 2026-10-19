import json

from fontTools.ttLib import TTFont
import pytest

from glyfetti.engine import build, FONTS_DIR
from glyfetti.validation import CHARSETS, validate_style


@pytest.fixture
def style():
    return {'name': 'test', 'font': str(FONTS_DIR / 'TitanOne-Regular.ttf'), 'size': 12, 'supersample': 1,
            'atlas_width': 1024, 'fill': {'stops': [[0, '#ffffff'], [1, '#ffcc00']]}, 'outline': {'color': '#000000', 'width': 1}}


def test_named_charsets_combine_with_chars(style):
    result = validate_style(dict(style, chars='Ω!A', charset=['ascii', 'latin-ext-a']))
    assert result['chars'].startswith('Ω!A')
    assert set(result['chars']) == set('Ω') | set(CHARSETS['ascii']) | set(CHARSETS['latin-ext-a'])
    assert len(result['chars']) == len(set(result['chars']))
    assert validate_style(result)['chars'] == result['chars']


def test_single_charset_without_chars(style):
    assert set(validate_style(dict(style, charset='polish'))['chars']) >= set('ĄąŻż„”')
    assert 'Я' in validate_style(dict(style, charset='cyrillic'))['chars']
    assert 'ÿ' in validate_style(dict(style, charset='latin1'))['chars']


@pytest.mark.parametrize('change', [{}, {'charset': 'klingon'}, {'charset': []}, {'charset': ['ascii', 'ascii']}])
def test_invalid_charset_is_rejected(style, change):
    with pytest.raises(ValueError):
        validate_style(dict(style, **change))


def test_simple_style_charset_replaces_default_chars(style):
    result = validate_style({'name': 'simple', 'simple': {}, 'charset': 'ascii'})
    assert set(result['chars']) == set(CHARSETS['ascii'])


def test_font_charset_renders_whole_cmap(style, tmp_path):
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(dict(style, charset='font', kerning=False)), 'utf-8')
    result = build(source, tmp_path / 'out', preview_only=False)
    with TTFont(style['font']) as font:
        expected = {c for c in font.getBestCmap() if chr(c).isprintable() and not chr(c).isspace()}
    ids = {c['id'] for c in json.loads((tmp_path / 'out/test.json').read_text())['chars']} - {32}
    assert ids == expected
    assert result['skipped'] == ''


def test_font_charset_guards_huge_fonts(style, tmp_path, monkeypatch):
    monkeypatch.setattr('glyfetti.engine.MAX_FONT_CHARS', 10)
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(dict(style, charset='font')), 'utf-8')
    with pytest.raises(ValueError, match='charset'):
        build(source, tmp_path / 'out')
