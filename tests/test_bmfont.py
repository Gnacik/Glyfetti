import json
import struct
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from glyfetti.cli import main
from glyfetti.engine import build, FONTS_DIR

INFO_KEYS = ('size', 'bold', 'italic', 'unicode', 'stretchH', 'smooth', 'aa', 'padding', 'spacing', 'face')
COMMON_KEYS = ('lineHeight', 'base', 'scaleW', 'scaleH', 'pages', 'packed')
CHAR_KEYS = ('id', 'x', 'y', 'width', 'height', 'xoffset', 'yoffset', 'xadvance', 'page', 'chnl')


def value(text):
    try:
        return int(text)
    except ValueError:
        return text


def normalize(info, common, pages, chars, kernings):
    return {'info': {k: info[k] for k in INFO_KEYS}, 'common': {k: common[k] for k in COMMON_KEYS}, 'pages': pages,
            'chars': [{k: c[k] for k in CHAR_KEYS} for c in chars],
            'kernings': [{k: p[k] for k in ('first', 'second', 'amount')} for p in kernings]}


def parse_text(data):
    tags = {}
    for line in data.decode('utf-8').splitlines():
        tag, *fields = line.split(' ')
        tags.setdefault(tag, []).append({k: value(v.strip('"')) for k, v in (f.split('=', 1) for f in fields)})
    return normalize(tags['info'][0], tags['common'][0], [p['file'] for p in tags['page']], tags.get('char', []), tags.get('kerning', []))


def parse_xml(data):
    root = ET.fromstring(data)

    def attrs(element):
        return {k: value(v) for k, v in element.attrib.items()}
    return normalize(attrs(root.find('info')), attrs(root.find('common')), [p.get('file') for p in root.iter('page')],
                     [attrs(c) for c in root.iter('char')], [attrs(k) for k in root.iter('kerning')])


def parse_binary(data):
    assert data[:4] == b'BMF\x03'
    blocks, offset = {}, 4
    while offset < len(data):
        kind, size = struct.unpack_from('<BI', data, offset)
        blocks[kind] = data[offset + 5:offset + 5 + size]
        offset += 5 + size
    size, bits, _, stretch, aa, *pad, sx, sy, _ = struct.unpack_from('<hBBHBBBBBBBB', blocks[1])
    info = {'size': size, 'smooth': bits >> 7 & 1, 'unicode': bits >> 6 & 1, 'italic': bits >> 5 & 1, 'bold': bits >> 4 & 1,
            'stretchH': stretch, 'aa': aa, 'padding': ','.join(map(str, pad)), 'spacing': f'{sx},{sy}', 'face': blocks[1][14:-1].decode()}
    line, base, w, h, pages, packed = struct.unpack_from('<HHHHHB', blocks[2])
    common = {'lineHeight': line, 'base': base, 'scaleW': w, 'scaleH': h, 'pages': pages, 'packed': packed >> 7}
    chars = [dict(zip(CHAR_KEYS, item)) for item in struct.iter_unpack('<IHHHHhhhBB', blocks[4])]
    kernings = [dict(zip(('first', 'second', 'amount'), item)) for item in struct.iter_unpack('<IIh', blocks.get(5, b''))]
    return normalize(info, common, [p.decode() for p in blocks[3].split(b'\0')[:-1]], chars, kernings)


@pytest.fixture
def style():
    return {'name': 'test', 'font': str(FONTS_DIR / 'TitanOne-Regular.ttf'), 'size': 24, 'supersample': 1, 'chars': 'AVTaoą',
            'atlas_width': 256, 'fill': {'stops': [[0, '#ffffff'], [1, '#ffcc00']]}, 'outline': {'color': '#000000', 'width': 1}}


def test_xml_and_binary_match_text(style, tmp_path):
    parsed = {}
    for fmt, parse in (('text', parse_text), ('xml', parse_xml), ('binary', parse_binary)):
        source = tmp_path / f'{fmt}.json'
        source.write_text(json.dumps(dict(style, fnt_format=fmt)), 'utf-8')
        build(source, tmp_path / fmt)
        parsed[fmt] = parse((tmp_path / fmt / 'test.fnt').read_bytes())
    assert parsed['text']['kernings']
    assert len(parsed['text']['chars']) == len(json.loads((tmp_path / 'text/test.json').read_text())['chars'])
    assert parsed['xml'] == parsed['text']
    assert parsed['binary'] == parsed['text']


def test_cli_fnt_format_overrides_style(style, tmp_path):
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(style), 'utf-8')
    assert main(['build', str(source), '-o', str(tmp_path / 'out'), '--fnt-format', 'binary']) == 0
    assert (tmp_path / 'out/test.fnt').read_bytes()[:4] == b'BMF\x03'


def test_invalid_fnt_format_is_rejected(style, tmp_path):
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(dict(style, fnt_format='json')), 'utf-8')
    with pytest.raises(ValueError, match='fnt_format'):
        build(source, tmp_path / 'out')


MULTI = dict(chars='ABCDEFGHIJKLMNOPąę', atlas_width=64, max_atlas_size=64, max_pages=64)


@pytest.mark.parametrize('method', ['maxrects', 'shelf'])
def test_multi_page_atlas_in_every_format(style, tmp_path, method):
    style = dict(style, **MULTI, atlas_packing=method)
    parsed, results = {}, {}
    for fmt, parse in (('text', parse_text), ('xml', parse_xml), ('binary', parse_binary)):
        source = tmp_path / f'{fmt}.json'
        source.write_text(json.dumps(dict(style, fnt_format=fmt)), 'utf-8')
        results[fmt] = build(source, tmp_path / fmt)
        parsed[fmt] = parse((tmp_path / fmt / 'test.fnt').read_bytes())
    assert parsed['xml'] == parsed['text']
    assert parsed['binary'] == parsed['text']
    font = parsed['text']
    metadata = json.loads((tmp_path / 'text/test.json').read_text())
    pages = metadata['pages']
    assert len(pages) >= 2 and results['text']['pages'] == len(pages)
    assert font['pages'] == pages == [f'test_{i}.png' for i in range(len(pages))]
    assert font['common']['pages'] == len(pages)
    assert not (tmp_path / 'text/test.png').exists()
    assert all((tmp_path / 'text' / f'test_{i}_atlas_on_white.png').exists() for i in range(len(pages)))
    width, height = font['common']['scaleW'], font['common']['scaleH']
    assert height <= 64
    images = [Image.open(tmp_path / 'text' / file) for file in pages]
    assert all(image.size == (width, height) for image in images)
    assert [(c['id'], c.get('page', 0), c['x'], c['y']) for c in metadata['chars']] == [(c['id'], c['page'], c['x'], c['y']) for c in font['chars']]
    glyphs = [c for c in font['chars'] if c['width']]
    assert {c['page'] for c in glyphs} == set(range(len(pages)))
    for i, c in enumerate(glyphs):
        assert 0 <= c['page'] < len(pages)
        assert 0 <= c['x'] and c['x'] + c['width'] <= width and 0 <= c['y'] and c['y'] + c['height'] <= height
        assert images[c['page']].getchannel('A').crop((c['x'], c['y'], c['x'] + c['width'], c['y'] + c['height'])).getbbox()
        for o in glyphs[i + 1:]:
            assert o['page'] != c['page'] or c['x'] + c['width'] <= o['x'] or o['x'] + o['width'] <= c['x'] or \
                c['y'] + c['height'] <= o['y'] or o['y'] + o['height'] <= c['y']


def test_single_page_output_keeps_plain_names(style, tmp_path):
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(style), 'utf-8')
    assert build(source, tmp_path / 'out')['pages'] == 1
    metadata = json.loads((tmp_path / 'out/test.json').read_text())
    assert 'pages' not in metadata and all('page' not in c for c in metadata['chars'])
    assert parse_text((tmp_path / 'out/test.fnt').read_bytes())['pages'] == ['test.png']


def test_max_pages_limits_spilling(style, tmp_path):
    source = tmp_path / 'style.json'
    source.write_text(json.dumps(dict(style, **dict(MULTI, max_pages=1))), 'utf-8')
    with pytest.raises(ValueError, match='max_atlas_size'):
        build(source, tmp_path / 'one')
    with pytest.raises(ValueError, match='max_pages'):
        build(source, tmp_path / 'two', max_pages=2)
    assert main(['build', str(source), '-o', str(tmp_path / 'cli'), '--max-pages', '64']) == 0
    assert (tmp_path / 'cli/test_0.png').exists()
