"""glyfetti command line interface."""
import argparse
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog='glyfetti', description='Styled game text & bitmap font atlas generator.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    b = sub.add_parser('build', help='render a style into atlas PNG + .fnt + .json + preview')
    b.add_argument('style', nargs='+', help='style JSON file(s)')
    b.add_argument('-o', '--out', help='output directory (default: <style dir>/out)')
    b.add_argument('--preview-only', action='store_true', help='render only the preview text (fast)')
    b.add_argument('-j', '--workers', type=int, help='glyph rendering threads (default: CPU count, 1 = sequential)')

    title = sub.add_parser('title', help='render whole text with shared effects into a transparent PNG')
    title.add_argument('style', help='style JSON; uses its preview text unless --text is given')
    title.add_argument('--text', help='title text; actual line breaks create multiple lines')
    title.add_argument('--align', choices=['left', 'center', 'right'])
    title.add_argument('-o', '--out', help='output PNG (default: <style dir>/out/<name>_title.png)')

    inspect = sub.add_parser('inspect', help='inspect rendered font atlas, metrics, Polish glyphs and clipping')
    inspect.add_argument('style', help='style JSON to inspect')
    inspect.add_argument('-o', '--out', help='save the inspection report as JSON')
    inspect.add_argument('--strict', action='store_true', help='return nonzero exit code if quality errors are found')

    reference = sub.add_parser('reference', help='extract fill colors and approximate outline from a PNG/JPG')
    reference.add_argument('image', help='local PNG or JPG with isolated lettering')
    reference.add_argument('--style', help='base style JSON (default: honey_gold preset)')
    reference.add_argument('-o', '--out', help='result JSON (default: <image>.style.json)')

    g = sub.add_parser('gallery', help='render all presets in a folder into one gallery PNG')
    g.add_argument('folder', nargs='?')
    g.add_argument('-o', '--out', default='gallery.png')

    p = sub.add_parser('patch', help='add missing Polish diacritics to a font (composite glyphs)')
    p.add_argument('src'); p.add_argument('dst')
    p.add_argument('--axes', default='', help='variable font location, e.g. wght=700,wdth=75')

    c = sub.add_parser('check-font', help='list characters missing from a font')
    c.add_argument('font')
    c.add_argument('--chars', default='ĄĆĘŁŃÓŚŹŻąćęłńóśźżÄÖÜäöüßÉÈÊéèêÇçÑñČŘŠŽčřšž€…„”«»')

    v = sub.add_parser('validate', help='validate style JSON without rendering')
    v.add_argument('style', nargs='+')

    expanded = sub.add_parser('expand', help='expand a simple or mixed style into a validated raw JSON file')
    expanded.add_argument('style')
    expanded.add_argument('-o', '--out', help='output JSON; defaults to stdout')

    server = sub.add_parser('serve', help='open the local style editor with live preview')
    server.add_argument('--port', type=int, default=8765)
    server.add_argument('--no-browser', action='store_true')

    mcp = sub.add_parser('mcp', help='run the optional MCP server over stdio (Python 3.11+)')
    mcp.add_argument('--output-dir', default='glyfetti-output', help='directory for exported artifacts')
    mcp.add_argument('--print-config', action='store_true', help='print a ready-to-copy client configuration instead of starting the server')

    a = ap.parse_args(argv)
    try:
        return run(a)
    except (ValueError, OSError, KeyError) as error:
        print(f'glyfetti: {error}', file=sys.stderr)
        return 2


def run(a):
    if a.cmd == 'mcp':
        from .mcp_server import connection_config, run_mcp
        if a.print_config:
            import json
            print(json.dumps(connection_config(a.output_dir), ensure_ascii=False, indent=2))
        else:
            run_mcp(a.output_dir)
    elif a.cmd == 'serve':
        from .server import serve
        serve(port=a.port, open_browser=not a.no_browser)
    elif a.cmd == 'expand':
        import json
        from .validation import validate_style
        source = Path(a.style)
        style = validate_style(json.loads(source.read_text('utf-8')))
        # Expanded files can move away from the original style directory.
        from .engine import resolve_font
        font_path, _ = resolve_font(dict(style, auto_diacritics=False), source.parent)
        style['font'] = str(font_path.resolve())
        content = json.dumps(style, ensure_ascii=False, indent=2) + '\n'
        if a.out:
            target = Path(a.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, 'utf-8')
        else:
            print(content, end='')
    elif a.cmd == 'inspect':
        import json
        from .quality import inspect_style
        source = Path(a.style)
        result = inspect_style(json.loads(source.read_text('utf-8')), base=source.parent)
        summary = result['summary']
        print(f"{result['name']}: {summary['glyphs']} glyphs, {summary['errors']} errors, "
              f"{summary['warnings']} warnings, {summary['missing']} missing, "
              f"{summary['clipped']} clipped, {summary['kerning_pairs']} kerning pairs")
        for issue in result['issues']:
            print(f"  {issue['severity']}: {issue.get('char', '-')!r} [{issue['code']}] {issue['message']}")
        if a.out:
            output = Path(a.out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
            print(f"Report: {output}")
        return 1 if a.strict and summary['errors'] else 0
    elif a.cmd == 'reference':
        import json
        from .engine import resolve_font
        from .reference import analyze_reference
        from .validation import DATA_DIR
        image = Path(a.image)
        base = Path(a.style) if a.style else DATA_DIR / 'presets' / 'honey_gold.json'
        source_style = json.loads(base.read_text('utf-8'))
        result = analyze_reference(image.read_bytes(), source_style)
        font_path, _ = resolve_font(dict(result['style'], auto_diacritics=False), base.parent)
        result['style']['font'] = str(font_path.resolve())
        output = Path(a.out) if a.out else image.with_suffix('.style.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result['style'], ensure_ascii=False, indent=2) + '\n', 'utf-8')
        print(f"Reference style saved: {output}")
        print(result['analysis']['warning'])
    elif a.cmd == 'validate':
        import json
        from .validation import validate_style
        for filename in a.style:
            validate_style(json.loads(Path(filename).read_text('utf-8')))
            print(f'{filename}: valid')
    elif a.cmd == 'title':
        from .title import build_title
        result = build_title(a.style, output=a.out, text=a.text, align=a.align)
        print(f"{result['name']}: title {result['size'][0]}x{result['size'][1]} -> {result['out']}")
        if result['skipped']:
            print(f"missing characters: {result['skipped']}", file=sys.stderr)
    elif a.cmd == 'build':
        from .engine import build
        for s in a.style:
            r = build(s, out_dir=a.out, preview_only=a.preview_only, workers=a.workers)
            msg = (f"{r['name']}: {r['glyphs']} glyphs, {r['kernings']} kerning pairs, "
                   f"atlas {r['atlas'][0]}x{r['atlas'][1]} ({r['packing']}, {r['occupancy']:.0%} occupied) -> {r['out']}")
            if r['skipped']:
                msg += f"  (not in font, skipped: {r['skipped']})"
            print(msg)
    elif a.cmd == 'gallery':
        from .gallery import make_gallery
        from .validation import DATA_DIR
        folder = a.folder or ('presets' if Path('presets').is_dir() else DATA_DIR / 'presets')
        print(make_gallery(folder, a.out))
    elif a.cmd == 'patch':
        from .patch import patch_font
        print('added:', patch_font(a.src, a.dst, a.axes) or '-')
    elif a.cmd == 'check-font':
        from .patch import missing_chars
        m = missing_chars(a.font, a.chars)
        print('missing:', m or 'none')
        return 1 if m else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
