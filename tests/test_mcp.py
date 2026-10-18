import base64
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

if sys.version_info < (3, 11):
    pytest.skip('Optional MCP SDK requires Python 3.11+', allow_module_level=True)
pytest.importorskip('mcp.server.mcpserver', reason='Install glyfetti[mcp] to test MCP')

from mcp import Client, StdioServerParameters
from PIL import Image

from glyfetti.mcp_server import create_server
from glyfetti.cli import main


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def client(tmp_path):
    async with Client(create_server(tmp_path / 'exports'), raise_exceptions=True) as connected:
        yield connected


def style():
    return {'name': 'protocol_test', 'simple': {'palette': 'mint'}, 'size': 24,
            'supersample': 1, 'chars': 'AVą', 'preview': ['AVą']}


def test_generated_config_uses_current_python_and_absolute_output(tmp_path, capsys):
    output = tmp_path / 'exports'
    assert main(['mcp', '--output-dir', str(output), '--print-config']) == 0
    config = json.loads(capsys.readouterr().out)['mcpServers']['glyfetti']
    assert Path(config['command']).samefile(sys.executable)
    assert config['args'] == ['-m', 'glyfetti.cli', 'mcp', '--output-dir', str(output.resolve())]
    assert not output.exists()


@pytest.mark.anyio
async def test_tool_discovery_presets_fonts_and_schema(client):
    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == {'list_presets', 'get_preset', 'list_fonts', 'check_font', 'expand_style', 'preview_style', 'export_style'}
    hints = {tool.name: tool.annotations for tool in tools}
    assert hints['get_preset'].read_only_hint
    assert not hints['export_style'].destructive_hint
    assert not hints['export_style'].idempotent_hint
    presets = (await client.call_tool('list_presets', {})).structured_content['result']
    assert len(presets) == 12
    preset = await client.call_tool('get_preset', {'name': 'honey_gold'})
    assert Path(preset.structured_content['font']).is_file()
    fonts = (await client.call_tool('list_fonts', {})).structured_content['result']
    assert len(fonts) == 6
    assert any(font['axes'] for font in fonts)
    schema = await client.read_resource('glyfetti://styles/schema')
    assert '$defs' in json.loads(schema.contents[0].text)


@pytest.mark.anyio
@pytest.mark.parametrize('mode', ['atlas', 'title'])
async def test_previews_are_inline_png_and_do_not_create_export_folders(client, tmp_path, mode):
    result = await client.call_tool('preview_style', {'style': style(), 'mode': mode, 'text': 'AVą'})
    assert not result.is_error
    assert result.structured_content['mode'] == mode
    image = next(block for block in result.content if block.type == 'image')
    assert image.mime_type == 'image/png'
    with Image.open(io.BytesIO(base64.b64decode(image.data))) as preview:
        assert preview.width > 0 and preview.height > 0
    assert not (tmp_path / 'exports').exists()


@pytest.mark.anyio
@pytest.mark.parametrize('mode', ['atlas', 'title'])
async def test_export_files_and_resources_contain_the_same_bytes(client, tmp_path, mode):
    result = await client.call_tool('export_style', {'style': style(), 'mode': mode})
    assert not result.is_error
    exported = result.structured_content
    assert exported['report']['skipped'] == ''
    assert len(exported['files']) == 2
    for artifact in exported['files']:
        path = Path(artifact['path'])
        assert path.resolve().is_relative_to((tmp_path / 'exports').resolve())
        resource = (await client.read_resource(artifact['uri'])).contents[0]
        raw = resource.text.encode() if hasattr(resource, 'text') else base64.b64decode(resource.blob)
        assert resource.mime_type == artifact['mime_type']
        assert raw == path.read_bytes()
    artifact = Path(exported['files'][0]['path'])
    if mode == 'atlas':
        with zipfile.ZipFile(artifact) as archive:
            assert 'protocol_test.fnt' in archive.namelist()
            assert json.loads(archive.read('build-report.json'))['glyphs'] == 3
    else:
        with Image.open(artifact) as image:
            assert image.getpixel((0, 0))[3] == 0


@pytest.mark.anyio
async def test_export_does_not_overwrite_previous_files(client):
    args = {'style': style(), 'mode': 'title'}
    first = (await client.call_tool('export_style', args)).structured_content
    path = Path(first['files'][0]['path'])
    original = path.read_bytes()
    second = (await client.call_tool('export_style', args)).structured_content
    assert first['export_id'] != second['export_id']
    assert path.read_bytes() == original


@pytest.mark.anyio
async def test_validation_errors_are_actionable_and_do_not_publish_exports(client, tmp_path):
    result = await client.call_tool('expand_style', {'style': {'name': 'bad', 'simple': {'shine': 2}}})
    assert result.is_error and 'shine' in result.content[0].text
    result = await client.call_tool('get_preset', {'name': '../private'})
    assert result.is_error and 'Unknown preset' in result.content[0].text
    result = await client.call_tool('export_style', {'style': style(), 'mode': 'wrong'})
    assert result.is_error
    assert not (tmp_path / 'exports').exists()


@pytest.mark.anyio
async def test_expansion_and_native_font_coverage(client):
    result = await client.call_tool('expand_style', {'style': style()})
    assert not result.is_error and 'simple' not in result.structured_content
    result = await client.call_tool('check_font', {'font': 'Chewy', 'chars': 'Aą😀'})
    assert not result.is_error
    assert 'A' not in result.structured_content['missing_native']
    assert 'ą' in result.structured_content['missing_native']
    assert '😀' in result.structured_content['missing_native']


@pytest.mark.anyio
@pytest.mark.parametrize('connection_mode', ['auto', 'legacy'])
async def test_mcp_stdio_subprocess_handshake_preview_export_and_readback(tmp_path, connection_mode):
    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'glyfetti.cli', 'mcp', '--output-dir', str(tmp_path / 'out')], cwd=tmp_path)
    async with Client(params, read_timeout_seconds=60, mode=connection_mode) as connected:
        names = {tool.name for tool in (await connected.list_tools()).tools}
        assert 'preview_style' in names
        preview = await connected.call_tool('preview_style', {'style': style(), 'mode': 'title'})
        assert not preview.is_error and any(block.type == 'image' for block in preview.content)
        exported = await connected.call_tool('export_style', {'style': style(), 'mode': 'title'})
        assert not exported.is_error
        resource = await connected.read_resource(exported.structured_content['files'][0]['uri'])
        assert base64.b64decode(resource.contents[0].blob).startswith(b'\x89PNG\r\n\x1a\n')
