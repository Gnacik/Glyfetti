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

    title = sub.add_parser('title', help='render whole text with shared effects into a transparent PNG')
    title.add_argument('style', help='style JSON; uses its preview text unless --text is given')
    title.add_argument('--text', help='title text; actual line breaks create multiple lines')
    title.add_argument('--align', choices=['left', 'center', 'right'])
    title.add_argument('-o', '--out', help='output PNG (default: <style dir>/out/<name>_title.png)')

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

    server = sub.add_parser('serve', help='open the local style editor with live preview')
    server.add_argument('--port', type=int, default=8765)
    server.add_argument('--no-browser', action='store_true')

    a = ap.parse_args(argv)
    try:
        return run(a)
    except (ValueError, OSError, KeyError) as error:
        print(f'glyfetti: {error}', file=sys.stderr)
        return 2


def run(a):
    if a.cmd == 'serve':
        from .server import serve
        serve(port=a.port, open_browser=not a.no_browser)
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
            r = build(s, out_dir=a.out, preview_only=a.preview_only)
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
