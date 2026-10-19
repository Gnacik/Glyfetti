"""Optional local MCP interface. stdout is reserved for the stdio protocol."""
import json
from pathlib import Path
import re
import sys
from typing import Any, Literal
import uuid

from fontTools.ttLib import TTFont, TTLibError

from .engine import resolve_font
from .patch import missing_chars
from .server import catalog, render_style
from .simple import FONTS
from .validation import DATA_DIR, validate_style


def artifact_path(root, export_id, filename):
    """Resolve only known artifact names inside one generated export directory."""
    root = Path(root).resolve()
    if not re.fullmatch(r'[0-9a-f]{32}', export_id) or filename not in ('style.json', 'title.png', 'atlas.zip'):
        raise ValueError('Unknown export artifact')
    folder = (root / export_id).resolve()
    path = (folder / filename).resolve()
    if folder.parent != root or path.parent != folder:
        raise ValueError('Export artifact is outside the configured output directory')
    if not path.is_file():
        raise ValueError('Export artifact does not exist; export the style first')
    return path


def create_server(output_dir='glyfetti-output'):
    if sys.version_info < (3, 11):
        raise ValueError('MCP requires Python 3.11 or newer; the CLI and editor still support Python 3.10.')
    try:
        from mcp.server import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
        from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
    except ImportError as error:
        raise ValueError('Install the optional MCP extra with: python -m pip install "glyfetti[mcp]" (or pip install -e ".[mcp]" from this repository).') from error
    from . import __version__
    root = Path(output_dir).expanduser().resolve()
    server = MCPServer(
        'Glyfetti', version=__version__, log_level='WARNING',
        instructions=(
            'Create styled bitmap font atlases or whole-title PNGs locally. Start with list_presets/get_preset '
            'or analyze_reference_image for colors from an isolated local title image, or a compact style such as {"name":"gold_title","simple":{"palette":"gold","shine":0.7}}. '
            'expand_style validates it and returns raw settings. Use preview_style to inspect the actual PNG, '
            'refine the style, then export_style to save full-quality artifacts. Use mode="title" for a '
            'shared outline around an entire title, or mode="atlas" for reusable glyphs and BMFont/Unity metrics. '
            'Text overrides preview lines and its characters are included in atlas exports. '
            'Read glyfetti://styles/schema for all parameters. Custom fonts may use absolute local paths. '
            'Exports return local file paths and MCP resource URIs; no credentials or network service are needed.'
        ),
    )
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    render_hint = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
    export_hint = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)

    def prepare(style, text=None):
        try:
            raw = validate_style(style)
            if text is not None:
                raw['preview'] = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
            raw['chars'] = ''.join(dict.fromkeys(raw['chars'] + ''.join(raw.get('preview', []))))
            raw = validate_style(raw)
            font_path, _ = resolve_font(dict(raw, auto_diacritics=False), Path.cwd())
            raw['font'] = str(font_path.resolve())
            return raw
        except (ValueError, OSError, KeyError, TTLibError) as error:
            raise ToolError(str(error)) from error

    def render(style, preview, mode):
        try:
            return render_style(style, preview=preview, mode=mode, with_report=not preview)
        except (ValueError, OSError, KeyError, TTLibError) as error:
            raise ToolError(str(error)) from error

    @server.tool(annotations=read_only)
    def list_presets() -> list[dict[str, Any]]:
        """List bundled looks; call get_preset(name) to retrieve an editable style."""
        return [{key: style.get(key, '') for key in ('name', 'description', 'font_label')} for style in catalog()['presets']]

    @server.tool(annotations=read_only)
    def get_preset(name: str) -> dict[str, Any]:
        """Retrieve one bundled style, including an absolute path to its bundled font."""
        for style in catalog()['presets']:
            if style['name'] == name:
                return validate_style(style)
        raise ToolError(f'Unknown preset: {name}. Use list_presets to see available names.')

    @server.tool(annotations=read_only)
    def list_fonts() -> list[dict[str, Any]]:
        """List bundled font aliases, local paths and variable-axis ranges."""
        result = []
        for name, filename in FONTS.items():
            path = DATA_DIR / 'fonts' / filename
            with TTFont(path) as font:
                axes = [{'tag': axis.axisTag, 'min': axis.minValue, 'default': axis.defaultValue, 'max': axis.maxValue}
                        for axis in font['fvar'].axes] if 'fvar' in font else []
            result.append({'name': name, 'path': str(path.resolve()), 'axes': axes})
        return result

    @server.tool(annotations=read_only)
    def check_font(font: str, chars: str) -> dict[str, Any]:
        """Report native missing characters in a bundled alias or local font. Builds may compose Polish accents."""
        raw = prepare({'name': 'font_check', 'font': font, 'chars': chars or ' ', 'simple': {}})
        try:
            return {'font': raw['font'], 'missing_native': missing_chars(raw['font'], chars)}
        except (ValueError, OSError, TTLibError) as error:
            raise ToolError(str(error)) from error

    @server.tool(annotations=read_only)
    def expand_style(style: dict[str, Any]) -> dict[str, Any]:
        """Validate simple/mixed/raw JSON and return full raw settings, without rendering or writing an export."""
        return prepare(style)

    @server.tool(annotations=render_hint)
    def preview_style(style: dict[str, Any], mode: Literal['atlas', 'title'] = 'atlas', text: str | None = None) -> CallToolResult:
        """Return an inline PNG and metrics using fast draft quality. Does not save export files."""
        raw = prepare(style, text)
        result = render(raw, True, mode)
        data = result.pop('image').partition(',')[2]
        result['mode'] = mode
        return CallToolResult(
            content=[TextContent(text=json.dumps(result, ensure_ascii=False)), ImageContent(data=data, mime_type='image/png')],
            structured_content=result,
        )

    @server.tool(annotations=export_hint)
    def export_style(style: dict[str, Any], mode: Literal['atlas', 'title'] = 'atlas', text: str | None = None) -> dict[str, Any]:
        """Save a full-quality atlas ZIP or transparent title PNG plus raw style JSON. Every call creates a new export folder."""
        raw = prepare(style, text)
        data, report = render(raw, False, mode)
        export_id = uuid.uuid4().hex
        filename, mime = ('title.png', 'image/png') if mode == 'title' else ('atlas.zip', 'application/zip')
        try:
            folder = root / export_id
            folder.mkdir(parents=True, exist_ok=False)
            (folder / filename).write_bytes(data)
            (folder / 'style.json').write_bytes((json.dumps(raw, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        except OSError as error:
            raise ToolError(f'Could not save export: {error}') from error
        files = [{'name': name, 'path': str(folder / name), 'uri': f'glyfetti://exports/{export_id}/{name}',
                  'mime_type': media, 'bytes': (folder / name).stat().st_size}
                 for name, media in ((filename, mime), ('style.json', 'application/json'))]
        return {'export_id': export_id, 'name': raw['name'], 'mode': mode, 'files': files, 'report': report}

    @server.tool(annotations=read_only)
    def analyze_reference_image(image: str, style: dict[str, Any]) -> dict[str, Any]:
        """Estimate fill gradient and outline from a local PNG/JPEG; keep the font and effect geometry."""
        from .reference import analyze_reference
        source = Path(image).expanduser()
        try:
            if source.stat().st_size > 4 * 1024 * 1024:
                raise ValueError('Reference image exceeds 4 MiB.')
            result = analyze_reference(source.read_bytes(), prepare(style))
            return result
        except (ValueError, OSError, KeyError, TTLibError) as error:
            raise ToolError(str(error)) from error

    @server.resource('glyfetti://styles/schema', mime_type='application/json')
    def style_schema() -> str:
        """JSON Schema for simple, mixed and raw Glyfetti styles."""
        return (DATA_DIR / 'schema/style.schema.json').read_text('utf-8')

    @server.resource('glyfetti://exports/{export_id}/style.json', mime_type='application/json')
    def exported_style(export_id: str) -> str:
        return artifact_path(root, export_id, 'style.json').read_text('utf-8')

    @server.resource('glyfetti://exports/{export_id}/title.png', mime_type='image/png')
    def exported_title(export_id: str) -> bytes:
        return artifact_path(root, export_id, 'title.png').read_bytes()

    @server.resource('glyfetti://exports/{export_id}/atlas.zip', mime_type='application/zip')
    def exported_atlas(export_id: str) -> bytes:
        return artifact_path(root, export_id, 'atlas.zip').read_bytes()

    return server


def run_mcp(output_dir='glyfetti-output'):
    create_server(output_dir).run(transport='stdio')


def connection_config(output_dir='glyfetti-output'):
    """Return a validated launch configuration without opening a connection."""
    create_server(output_dir)
    return {'mcpServers': {'glyfetti': {
        'command': sys.executable,
        'args': ['-m', 'glyfetti.cli', 'mcp', '--output-dir', str(Path(output_dir).expanduser().resolve())],
    }}}
