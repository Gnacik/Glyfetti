import copy
import json
import random

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0
from PIL import Image, ImageFont, features
import pytest

from glyfetti.engine import build, FONTS_DIR
from glyfetti.kerning import read_kerning
from glyfetti.packing import pack_atlas, pack_pages, shelf_pack


def custom_font(tmp_path, feature=None):
    font = TTFont(FONTS_DIR / 'TitanOne-Regular.ttf')
    for table in ('GPOS', 'kern'):
        if table in font:
            del font[table]
    if feature:
        addOpenTypeFeaturesFromString(font, feature)
    path = tmp_path / 'font.ttf'
    font.save(path)
    return path


def pairs(path, chars='AVTo ', **kwargs):
    return {(p['first'], p['second']): p['amount'] for p in read_kerning(path, chars, 100, **kwargs)}


def test_explicit_and_class_gpos_pairs_are_scaled_and_filtered(tmp_path):
    path = custom_font(tmp_path, 'feature kern { pos A V -120; @Left=[T]; @Right=[o a]; pos @Left @Right -80; } kern;')
    assert pairs(path) == {(65, 86): -12, (84, 111): -8}
    assert pairs(path, condense=.5) == {(65, 86): -6, (84, 111): -4}


def test_extension_lookup(tmp_path):
    path = custom_font(tmp_path, 'lookup K useExtension { pos A V -120; } K; feature kern { lookup K; } kern;')
    assert pairs(path) == {(65, 86): -12}


def test_zero_record_blocks_later_subtable_but_distinct_lookups_add(tmp_path):
    path = custom_font(tmp_path, 'lookup K { pos A V -120; } K; lookup L { pos A V -30; } L; feature kern { lookup K; lookup L; } kern;')
    assert pairs(path) == {(65, 86): -15}
    with TTFont(path) as font:
        lookup = font['GPOS'].table.LookupList.Lookup[0]
        original = copy.deepcopy(lookup.SubTable[0])
        lookup.SubTable[0].PairSet[0].PairValueRecord[0].Value1.XAdvance = 0
        lookup.SubTable.append(original)
        lookup.SubTableCount = len(lookup.SubTable)
        font.save(path)
    assert pairs(path) == {(65, 86): -3}


def test_class_zero_includes_unclassified_exported_glyphs(tmp_path):
    path = custom_font(tmp_path, 'feature kern { @L=[A]; @R=[V]; pos @L @R -100; } kern;')
    with TTFont(path) as font:
        table = font['GPOS'].table.LookupList.Lookup[0].SubTable[0]
        assert table.Format == 2
        first_class = table.ClassDef1.classDefs.get('A', 0)
        row = table.Class1Record[first_class]
        record = copy.deepcopy(row.Class2Record[1])
        record.Value1.XAdvance = -50
        row.Class2Record[0] = record
        font.save(path)
    assert pairs(path, 'AVB') == {(65, 65): -5, (65, 66): -5, (65, 86): -10}


def test_script_features_are_selected_without_double_applying(tmp_path):
    path = custom_font(tmp_path, 'languagesystem latn dflt; languagesystem cyrl dflt; feature kern { script latn; pos A V -100; script cyrl; pos A V -200; } kern;')
    assert pairs(path) == {(65, 86): -10}
    assert pairs(path, script='cyrl') == {(65, 86): -20}


def test_unsupported_placement_is_reported_instead_of_exporting_wrong_pair(tmp_path):
    path = custom_font(tmp_path, 'feature kern { pos A V <10 0 -120 0>; } kern;')
    with pytest.warns(UserWarning, match='cannot be represented'):
        assert pairs(path) == {}


def test_lookup_flags_exclude_ignored_marks(tmp_path):
    path = custom_font(tmp_path, 'table GDEF { GlyphClassDef [A V], , [acute], ; } GDEF; feature kern { lookupflag IgnoreMarks; @R=[V acute]; pos A @R -100; } kern;')
    with TTFont(path) as font:
        for cmap in font['cmap'].tables:
            if cmap.isUnicode():
                cmap.cmap[0xE001] = 'acute'
        font.save(path)
    assert pairs(path, 'AV\ue001') == {(65, 86): -10}


def test_legacy_kern_and_unicode_aliases(tmp_path):
    path = custom_font(tmp_path)
    with TTFont(path) as font:
        table = newTable('kern')
        table.version = 0
        subtable = KernTable_format_0()
        subtable.version, subtable.coverage = 0, 1
        subtable.kernTable = {('A', 'V'): -100}
        table.kernTables = [subtable]
        font['kern'] = table
        for cmap in font['cmap'].tables:
            if cmap.isUnicode():
                cmap.cmap[0xE000] = 'A'
        font.save(path)
    assert pairs(path, 'AV\ue000') == {(65, 86): -10, (0xE000, 86): -10}


@pytest.mark.skipif(not features.check_feature('raqm'), reason='Independent shaping oracle requires RAQM')
@pytest.mark.parametrize('filename', sorted(p.name for p in FONTS_DIR.glob('*.ttf')))
def test_bundled_font_kerning_matches_independent_pillow_shaping(filename):
    path = FONTS_DIR / filename
    font = ImageFont.truetype(str(path), 100)
    exported = pairs(path, 'AVToWa ')
    for text in ('AV', 'To', 'Wa', 'oV', ' A'):
        expected = round(font.getlength(text, features=['kern', '-liga', '-clig']) - font.getlength(text, features=['-kern', '-liga', '-clig']))
        assert exported.get(tuple(map(ord, text)), 0) == expected


@pytest.mark.skipif(not features.check_feature('raqm'), reason='Independent shaping oracle requires RAQM')
@pytest.mark.parametrize('weight', [200, 800])
def test_variable_kerning_matches_selected_weight(weight):
    path = FONTS_DIR / 'Dosis.ttf'
    font = ImageFont.truetype(str(path), 100)
    font.set_variation_by_axes([weight])
    exported = pairs(path, variation={'wght': weight})
    expected = round(font.getlength('AV', features=['kern']) - font.getlength('AV', features=['-kern']))
    assert exported[65, 86] == expected


def test_export_and_preview_use_the_same_kerning(tmp_path):
    path = custom_font(tmp_path, 'feature kern { pos A V -120; } kern;')
    style = {'name': 'pair', 'font': str(path), 'size': 100, 'supersample': 1,
             'chars': 'AV', 'preview': ['AV'], 'preview_bg': 'transparent',
             'outline': {'width': 0, 'color': '#000000'}, 'fill': {'stops': [[0, '#ffffff']]}}
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(style), 'utf-8')
    result = build(source, tmp_path / 'kerned')
    assert result['kernings'] == 1
    metadata = json.loads((tmp_path / 'kerned/pair.json').read_text())
    assert metadata['kernings'] == [{'first': 65, 'second': 86, 'amount': -12}]
    assert 'kerning first=65 second=86 amount=-12' in (tmp_path / 'kerned/pair.fnt').read_text()
    style['kerning'] = False
    source.write_text(json.dumps(style), 'utf-8')
    result = build(source, tmp_path / 'plain')
    assert result['kernings'] == 0
    with Image.open(tmp_path / 'kerned/pair_preview.png') as kerned, Image.open(tmp_path / 'plain/pair_preview.png') as plain:
        assert plain.width - kerned.width == 12


def test_maxrects_halves_the_atlas_and_fits_a_limit_shelf_cannot():
    sizes = [(70, 20), (20, 70)] * 3
    assert shelf_pack(sizes, 128, 2)[1] == 256
    assert pack_atlas(sizes, 128, max_height=128)[1:] == (128, 'maxrects')
    with pytest.raises(ValueError):
        pack_atlas(sizes, 128, max_height=128, method='shelf')


@pytest.mark.parametrize('seed', range(12))
def test_packing_is_deterministic_in_bounds_and_has_no_overlap(seed):
    randomizer = random.Random(seed)
    sizes = [(randomizer.randint(4, 110), randomizer.randint(4, 100)) for _ in range(40)]
    positions, height, method = pack_atlas(sizes, 256)
    assert pack_atlas(sizes, 256) == (positions, height, method)
    assert height <= shelf_pack(sizes, 256, 2)[1]
    for index, ((x, y), (w, h)) in enumerate(zip(positions, sizes)):
        assert 2 <= x and x + w <= 254
        assert 2 <= y and y + h <= height - 2
        for (other_x, other_y), (other_w, other_h) in zip(positions[index + 1:], sizes[index + 1:]):
            assert x + w + 2 <= other_x or other_x + other_w + 2 <= x or y + h + 2 <= other_y or other_y + other_h + 2 <= y


def test_maxrects_rejects_oversized_glyphs():
    with pytest.raises(ValueError, match='glyph width'):
        pack_atlas([(200, 10)], 128)
    with pytest.raises(ValueError, match='glyph height'):
        pack_atlas([(10, 200)], 128, max_height=128)


@pytest.mark.parametrize('method', ['maxrects', 'shelf'])
@pytest.mark.parametrize('seed', range(4))
def test_pages_spill_in_bounds_without_overlap(seed, method):
    randomizer = random.Random(seed)
    sizes = [(randomizer.randint(4, 60), randomizer.randint(4, 60)) for _ in range(60)]
    positions, height, _, pages = pack_pages(sizes, 128, 2, 128, method, 64)
    assert pages >= 2 and height <= 128
    assert {page for page, _, _ in positions} == set(range(pages))
    for index, ((page, x, y), (w, h)) in enumerate(zip(positions, sizes)):
        assert 2 <= x and x + w <= 128 and 2 <= y and y + h <= height - 2
        for (other_page, other_x, other_y), (other_w, other_h) in zip(positions[index + 1:], sizes[index + 1:]):
            assert other_page != page or x + w + 2 <= other_x or other_x + other_w + 2 <= x or y + h + 2 <= other_y or other_y + other_h + 2 <= y


def test_pages_keep_single_page_packing_and_honor_max_pages():
    sizes = [(70, 20), (20, 70)] * 3
    assert pack_pages(sizes, 128, max_height=128) == ([(0, x, y) for x, y in pack_atlas(sizes, 128, max_height=128)[0]], 128, 'maxrects', 1)
    with pytest.raises(ValueError, match='max_pages'):
        pack_pages([(60, 60)] * 20, 128, max_height=128, max_pages=2)
    with pytest.raises(ValueError, match='glyph height'):
        pack_pages([(10, 200)], 128, max_height=128)
