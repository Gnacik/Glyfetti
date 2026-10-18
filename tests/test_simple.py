import copy
import json
from pathlib import Path

from jsonschema import validate
from PIL import Image
import pytest

from glyfetti.cli import main
from glyfetti.engine import build, FONTS_DIR
from glyfetti.server import render_style
from glyfetti.simple import FONTS, PALETTES
from glyfetti.title import build_title
from glyfetti.validation import DATA_DIR, validate_style


def compact(**options):
    return {'name': 'simple', 'size': 24, 'supersample': 1, 'chars': 'AVą',
            'preview': ['AVą'], 'simple': options}


def test_defaults_are_complete_deterministic_and_do_not_modify_input():
    source = {'name': 'default', 'simple': {}}
    original = copy.deepcopy(source)
    raw = validate_style(source)
    assert source == original
    assert 'simple' not in raw
    assert raw['size'] == 90
    assert raw['font'] == str((FONTS_DIR / 'TitanOne-Regular.ttf').resolve())
    assert validate_style(raw) == raw == validate_style(source)


@pytest.mark.parametrize('palette', PALETTES)
def test_named_palettes_preserve_their_fill_stops(palette):
    raw = validate_style(compact(palette=palette))
    assert [color for position, color in raw['fill']['stops']] == PALETTES[palette][0]


@pytest.mark.parametrize('font,filename', FONTS.items())
def test_bundled_font_names_resolve_without_a_working_directory(font, filename):
    source = compact()
    source['font'] = font
    assert validate_style(source)['font'] == str((FONTS_DIR / filename).resolve())


def test_custom_color_wins_over_palette_and_derives_valid_colors():
    raw = validate_style(compact(palette='silver', base_color='#53c7a4'))
    assert raw['fill']['stops'][-1] == [1, '#53C7A4']
    assert len(raw['fill']['stops']) == 3
    assert raw['side']['color_top'] != raw['outline']['color']


def test_raw_overrides_merge_recursively_and_arrays_replace_in_full():
    source = compact(shine=.8)
    source.update(outline={'width': 7}, bevel={'highlight_strength': .1},
                  fill={'stops': [[0, '#123456']]}, jitter=None, tracking=9)
    raw = validate_style(source)
    assert raw['outline']['width'] == 7 and 'color' in raw['outline']
    assert raw['bevel']['highlight_strength'] == .1 and raw['bevel']['shadow_strength'] > 0
    assert raw['fill']['stops'] == [[0, '#123456']]
    assert raw['jitter'] is None
    assert raw['tracking'] == 9


def test_zero_effects_are_disabled_and_glow_replaces_shadow():
    raw = validate_style(compact(depth_3d=0, shine=0, playful=0, outline='none', shadow='none'))
    assert not raw['side']['enabled'] and not raw['bevel']['enabled'] and not raw['gloss']['enabled']
    assert raw['jitter'] is None and raw['outline']['width'] == 0 and not raw['shadow']['enabled']
    glow = validate_style(compact(shadow='none', glow='#FFAA00'))['shadow']
    assert glow['enabled'] and glow['dx'] == glow['dy'] == 0 and glow['color'] == '#FFAA00'


@pytest.mark.parametrize('size', [8, 90, 512])
def test_extreme_valid_sizes_and_full_effects_still_expand_to_valid_raw(size):
    source = compact(depth_3d=1, shine=1, playful=1, outline_width=40, weight=6, shadow='long')
    source['size'] = size
    raw = validate_style(source)
    assert raw['outline']['width'] == 40  # Numeric widths are final pixels.
    assert raw['side']['depth'] <= 40


@pytest.mark.parametrize('options,field', [
    ({'depth_3d': 2}, 'depth_3d'), ({'shine': True}, 'shine'), ({'palette': 'unknown'}, 'palette'),
    ({'base_color': 'red'}, 'base_color'), ({'weight': -1}, 'weight'), ({'shnie': .5}, 'simple'),
    ({'shine': float('nan')}, 'shine'),
])
def test_bad_simple_parameters_are_rejected_before_expansion(options, field):
    with pytest.raises(ValueError, match=field):
        validate_style(compact(**options))


def test_invalid_raw_overrides_and_globals_remain_errors():
    source = compact()
    source['outline'] = {'colro': '#000000'}
    with pytest.raises(ValueError, match='outline'):
        validate_style(source)
    source = compact()
    source['size'] = 'large'
    with pytest.raises(ValueError, match='size'):
        validate_style(source)


def test_schema_accepts_both_compact_and_raw_and_rejects_bad_simple_options():
    schema = json.loads((DATA_DIR / 'schema/style.schema.json').read_text('utf-8'))
    source = compact(shine=.8)
    source['outline'] = {'width': 2}
    validate(source, schema)
    validate(validate_style(source), schema)
    from jsonschema import ValidationError
    with pytest.raises(ValidationError):
        validate(compact(palette='unknown'), schema)


def test_raw_preset_keeps_its_existing_values():
    source = json.loads((DATA_DIR / 'presets/honey_gold.json').read_text('utf-8'))
    assert validate_style(source) == source


def test_compact_and_expanded_render_identical_atlas_and_title_images(tmp_path):
    source = compact(base_color='#53C7A4', playful=.3)
    path = tmp_path / 'simple.json'
    path.write_text(json.dumps(source), 'utf-8')
    expanded = tmp_path / 'expanded.json'
    expanded.write_text(json.dumps(validate_style(source)), 'utf-8')
    build(path, tmp_path / 'a')
    build(expanded, tmp_path / 'b')
    assert (tmp_path / 'a/simple.png').read_bytes() == (tmp_path / 'b/simple.png').read_bytes()
    first = build_title(path, tmp_path / 'first.png')
    second = build_title(expanded, tmp_path / 'second.png')
    assert first['out'].read_bytes() == second['out'].read_bytes()


def test_expand_cli_stdout_and_file_can_be_built_after_moving(tmp_path, capsys):
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(compact()), 'utf-8')
    assert main(['expand', str(source)]) == 0
    raw = json.loads(capsys.readouterr().out)
    assert 'simple' not in raw and Path(raw['font']).is_absolute()
    output = tmp_path / 'elsewhere' / 'expanded.json'
    assert main(['expand', str(source), '-o', str(output)]) == 0
    assert main(['build', str(output)]) == 0


def test_server_can_render_compact_styles_in_both_modes():
    source = compact(palette='magic', shine=.7)
    assert render_style(source, preview=True)['glyphs'] == 3
    assert render_style(source, preview=True, mode='title')['mode'] == 'title'


def test_both_color_extremes_expand_and_render(tmp_path):
    for color in ('#000000', '#FFFFFF'):
        source = compact(base_color=color)
        path = tmp_path / (color[1:] + '.json')
        path.write_text(json.dumps(source), 'utf-8')
        result = build_title(path)
        with Image.open(result['out']) as image:
            assert image.getbbox()
