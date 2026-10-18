import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import pytest

from glyfetti.server import catalog, make_server, render_style


def small_style():
    style = catalog()['presets'][0]
    style.update(size=16, supersample=1, chars='Aą', preview=['Aą'])
    for layer in ('side', 'bevel', 'shadow', 'gloss', 'extrude'):
        style[layer] = {'enabled': False}
    style.pop('variation', None)
    return style


def test_editor_preview_and_export_are_real_rendered_assets():
    style = small_style()
    preview = render_style(style, preview=True)
    assert preview['image'].startswith('data:image/png;base64,iVBOR')
    assert preview['glyphs'] == 2
    with zipfile.ZipFile(io.BytesIO(render_style(style))) as archive:
        name = style['name']
        assert {f'{name}.png', f'{name}.fnt', f'{name}.json', f'{name}.style.json'} <= set(archive.namelist())
        assert json.loads(archive.read(f'{name}.style.json')) == style


def test_editor_rejects_foreign_hosts_and_unauthenticated_writes():
    with make_server(0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(url + '/api/catalog') as response:
                data = json.load(response)
            with pytest.raises(HTTPError) as error:
                urlopen(Request(url + '/api/preview', data=b'{}', method='POST'))
            assert error.value.code == 403
            with pytest.raises(HTTPError) as error:
                urlopen(Request(url + '/', headers={'Host': 'foreign.example'}))
            assert error.value.code == 403
            with pytest.raises(HTTPError) as error:
                urlopen(Request(url + '/api/preview', data=b'{', headers={'X-Glyfetti-Token': data['token']}))
            assert error.value.code == 400
            request = Request(url + '/api/preview', data=json.dumps(small_style()).encode(), headers={'X-Glyfetti-Token': data['token']})
            with urlopen(request) as response:
                assert json.load(response)['glyphs'] == 2
            request = Request(url + '/api/title-export', data=json.dumps(small_style()).encode(), headers={'X-Glyfetti-Token': data['token']})
            with urlopen(request) as response:
                assert response.headers['Content-Type'] == 'image/png'
                assert response.read().startswith(b'\x89PNG\r\n\x1a\n')
            with urlopen(url + '/') as response:
                assert b'Type playground' in response.read()
        finally:
            server.shutdown()
            worker.join(timeout=5)


def test_only_one_editor_can_own_a_port():
    with make_server(0) as server:
        with pytest.raises(OSError):
            make_server(server.server_port)
