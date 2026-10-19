import json
import struct
import xml.etree.ElementTree as ET

import pytest

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
