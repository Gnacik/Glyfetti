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

    g = sub.add_parser('gallery', help='render all presets in a folder into one gallery PNG')
    g.add_argument('folder', nargs='?', default='presets')
    g.add_argument('-o', '--out', default='gallery.png')

    p = sub.add_parser('patch', help='add missing Polish diacritics to a font (composite glyphs)')
    p.add_argument('src'); p.add_argument('dst')
    p.add_argument('--axes', default='', help='variable font location, e.g. wght=700,wdth=75')

    c = sub.add_parser('check-font', help='list characters missing from a font')
    c.add_argument('font')
    c.add_argument('--chars', default='ĄĆĘŁŃÓŚŹŻąćęłńóśźżÄÖÜäöüßÉÈÊéèêÇçÑñČŘŠŽčřšž€…„”«»')

    a = ap.parse_args(argv)
    if a.cmd == 'build':
        from .engine import build
        for s in a.style:
            r = build(s, out_dir=a.out, preview_only=a.preview_only)
            msg = f"{r['name']}: {r['glyphs']} glyphs, atlas {r['atlas'][0]}x{r['atlas'][1]} -> {r['out']}"
            if r['skipped']:
                msg += f"  (not in font, skipped: {r['skipped']})"
            print(msg)
    elif a.cmd == 'gallery':
        from .gallery import make_gallery
        print(make_gallery(a.folder, a.out))
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
