"""Validate styles before allocating render buffers or writing output files."""
import copy
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT if (ROOT / 'schema/style.schema.json').is_file() else Path(__file__).parent / 'data'

ASCII = ''.join(map(chr, range(0x20, 0x7F)))
CHARSETS = {
    'ascii': ASCII,
    'latin1': ASCII + ''.join(map(chr, range(0xA1, 0x100))),
    'latin-ext-a': ''.join(map(chr, range(0x100, 0x180))),
    'cyrillic': ''.join(map(chr, [*range(0x400, 0x460), 0x490, 0x491])),
    'polish': ASCII + 'ĄĆĘŁŃÓŚŹŻąćęłńóśźż„”«»–—…€',
}


def charset_chars(style):
    names = style.get('charset', [])
    names = [names] if isinstance(names, str) else names
    return ''.join(dict.fromkeys(style.get('chars', '') + ''.join(CHARSETS.get(name, '') for name in names)))


def validate_style(style):
    """Accept either source format and return an independent normalized raw style."""
    schema = json.loads((DATA_DIR / 'schema/style.schema.json').read_text('utf-8'))
    raw_schema = schema['$defs']['raw']

    def check(definition, value, prefix=''):
        errors = sorted(Draft202012Validator(definition).iter_errors(value), key=lambda e: str(list(e.path)))
        if errors:
            error = errors[0]
            field = '.'.join(filter(None, [prefix, *map(str, error.path)])) or 'style'
            raise ValueError(f'{field}: {error.message}')

    def finite(value, path='style'):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f'{path}: must be a finite number')
        if isinstance(value, dict):
            for key, item in value.items():
                finite(item, f'{path}.{key}')
        elif isinstance(value, list):
            for index, item in enumerate(value):
                finite(item, f'{path}.{index}')

    finite(style)
    if isinstance(style, dict) and 'simple' in style:
        from .simple import expand_simple
        check(schema['$defs']['simple']['properties']['simple'], style['simple'], 'simple')
        globals_schema = {key: definition for key, definition in raw_schema['properties'].items()
                          if key not in ('fill', 'outline', 'side', 'bevel', 'gloss', 'shadow', 'extrude')}
        check({'type': 'object', 'properties': globals_schema}, style)
        style = expand_simple(style)
    check(raw_schema, style)
    positions = [stop[0] for stop in style['fill']['stops']]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise ValueError('fill.stops: positions must be strictly increasing')
    # JSON Schema accepts 24.0 as an integer; Pillow and bitwise seeds require int.
    style = copy.deepcopy(style)
    for key in ('size', 'supersample', 'atlas_width', 'max_atlas_size', 'order'):
        if key in style:
            style[key] = int(style[key])
    style['chars'] = charset_chars(style) or ' '
    if style.get('jitter') and 'seed' in style['jitter']:
        style['jitter']['seed'] = int(style['jitter']['seed'])
    return style
