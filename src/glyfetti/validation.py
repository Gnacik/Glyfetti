"""Validate styles before allocating render buffers or writing output files."""
import copy
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT if (ROOT / 'schema/style.schema.json').is_file() else Path(__file__).parent / 'data'


def validate_style(style):
    schema = json.loads((DATA_DIR / 'schema/style.schema.json').read_text('utf-8'))
    errors = sorted(Draft202012Validator(schema).iter_errors(style), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        field = '.'.join(map(str, error.path)) or 'style'
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
    positions = [stop[0] for stop in style['fill']['stops']]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise ValueError('fill.stops: positions must be strictly increasing')
    # JSON Schema accepts 24.0 as an integer; Pillow and bitwise seeds require int.
    style = copy.deepcopy(style)
    for key in ('size', 'supersample', 'atlas_width', 'max_atlas_size', 'order'):
        if key in style:
            style[key] = int(style[key])
    if style.get('jitter') and 'seed' in style['jitter']:
        style['jitter']['seed'] = int(style['jitter']['seed'])
    return style
