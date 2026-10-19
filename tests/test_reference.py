"""Reference-image palette extraction regression tests."""
import base64
from io import BytesIO
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont
import pytest

from glyfetti.cli import main
from glyfetti.engine import FONTS_DIR
from glyfetti.reference import MAX_REFERENCE_BYTES, analyze_reference
from glyfetti.server import make_server
from glyfetti.validation import validate_style


def _style():
    return {'name': 'from_reference', 'size': 52, 'chars': 'AĄB',
            'preview': ['AĄB'], 'simple': {'palette': 'gold'}}


def _image_bytes(mode='RGBA', outline=True):
    image = Image.new(mode, (340, 120), (0, 0, 0, 0) if mode == 'RGBA' else '#FAFAFA')
    font = ImageFont.truetype(str(FONTS_DIR / 'TitanOne-Regular.ttf'), 64)
    paint = ImageDraw.Draw(image)
    paint.text((20, 14), 'ABC', font=font, fill='#F0C048',
               stroke_width=5 if outline else 0, stroke_fill='#352018')
    stream = BytesIO()
    image.save(stream, 'PNG' if mode == 'RGBA' else 'JPEG', quality=97)
    return stream.getvalue()


def test_transparent_image_extracts_outline_and_preserves_font_and_effects():
    original = validate_style(_style())
    result = analyze_reference(_image_bytes(), _style())
    style, analysis = result['style'], result['analysis']
    assert analysis['segmentation'] == 'alpha'
    assert analysis['outline_detected']
    assert style['outline']['width'] > 0
    assert style['outline']['color'].startswith('#')
    assert len(style['fill']['stops']) == 3
    assert style['font'] == original['font']
    assert style['preview'] == original['preview']
    assert style['side']['depth'] == original['side']['depth']
    assert validate_style(style) == style


def test_flat_jpeg_background_and_absent_outline():
    result = analyze_reference(_image_bytes('RGB', outline=False), _style())
    assert result['analysis']['segmentation'] == 'background'
    assert result['style']['fill']['stops'][1][1].startswith('#')
    assert result['style']['outline']['width'] == 0


@pytest.mark.parametrize('image', [b'', b'not-an-image', b'x' * (MAX_REFERENCE_BYTES + 1)])
def test_invalid_or_oversized_image_is_rejected(image):
    with pytest.raises(ValueError):
        analyze_reference(image, _style())


def test_solid_background_without_foreground_is_rejected():
    stream = BytesIO()
    Image.new('RGB', (200, 100), '#F0F0F0').save(stream, format='PNG')
    with pytest.raises(ValueError, match='No clear lettering'):
        analyze_reference(stream.getvalue(), _style())


def test_cli_writes_reusable_json_style(tmp_path, capsys):
    src = tmp_path / 'reference.png'
    src.write_bytes(_image_bytes())
    out = tmp_path / 'result.json'
    assert main(['reference', str(src), '-o', str(out)]) == 0
    style = json.loads(out.read_text('utf-8'))
    assert Path(style['font']).exists()
    assert validate_style(style) == style
    assert 'saved' in capsys.readouterr().out.lower()


def test_authenticated_reference_http_endpoint_and_bad_upload():
    with make_server(0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(url + '/api/catalog') as response:
                token = json.load(response)['token']
            payload = json.dumps({
                'style': _style(),
                'image': 'data:image/png;base64,' + base64.b64encode(_image_bytes()).decode(),
            }).encode()
            req = Request(url + '/api/reference', data=payload,
                          headers={'X-Glyfetti-Token': token, 'Content-Type': 'application/json'})
            with urlopen(req) as response:
                data = json.load(response)
            assert validate_style(data['style']) == data['style']
            assert data['analysis']['outline_detected']

            with pytest.raises(HTTPError) as missing_token:
                urlopen(Request(url + '/api/reference', data=payload, method='POST'))
            assert missing_token.value.code == 403

            bad = Request(url + '/api/reference', data=json.dumps({'style': _style(), 'image': 'xyz'}).encode(),
                          headers={'X-Glyfetti-Token': token, 'Content-Type': 'application/json'})
            with pytest.raises(HTTPError) as invalid:
                urlopen(bad)
            assert invalid.value.code == 400
        finally:
            server.shutdown()
            thread.join(timeout=5)
