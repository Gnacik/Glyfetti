"""Add missing Polish diacritics (ĄĆĘŃŚŹŻąćęńśźż) to a TTF font as composite glyphs.

Requires the font to contain 'acute', 'dotaccent', 'ogonek' glyphs and Ó/ó (used to
measure accent height). Variable fonts are first instanced at the given axis location.

  glyfetti patch Chewy-Regular.ttf ChewyPL.ttf
  glyfetti patch Fredoka.ttf FredokaPL.ttf --axes wght=600,wdth=100
"""
import argparse
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent

PL = {  # znak: (baza, akcent, tryb)
    'Ą': ('A', 'ogonek', 'right'), 'Ę': ('E', 'ogonek', 'right'),
    'ą': ('a', 'ogonek', 'right'), 'ę': ('e', 'ogonek', 'center'),
    'Ć': ('C', 'acute', 'top'), 'Ń': ('N', 'acute', 'top'), 'Ś': ('S', 'acute', 'top'),
    'Ź': ('Z', 'acute', 'top'), 'Ż': ('Z', 'dotaccent', 'top'),
    'ć': ('c', 'acute', 'top'), 'ń': ('n', 'acute', 'top'), 'ś': ('s', 'acute', 'top'),
    'ź': ('z', 'acute', 'top'), 'ż': ('z', 'dotaccent', 'top'),
}


def bounds(glyf, name):
    g = glyf[name]
    g.recalcBounds(glyf)
    return g.xMin, g.yMin, g.xMax, g.yMax


def mark_bottom_from(font, glyf, cm, ch):
    """Accent bottom in the existing Ó/ó = top of Ó minus accent height."""
    top = bounds(glyf, cm[ord(ch)])[3]
    ax0, ay0, ax1, ay1 = bounds(glyf, 'acute')
    return top - (ay1 - ay0)


def patch_font(src, dst, axes=''):
    """Compose missing Polish letters from base glyphs + accents. Returns added characters."""
    font = TTFont(src)
    if 'fvar' in font:
        from fontTools.varLib import instancer
        if isinstance(axes, dict):
            loc = {k: float(v) for k, v in axes.items()}
        else:
            loc = {k: float(v) for k, v in (p.split('=') for p in axes.split(',') if p)}
        loc = {ax.axisTag: loc.get(ax.axisTag, ax.defaultValue) for ax in font['fvar'].axes}
        font = instancer.instantiateVariableFont(font, loc)
    if 'glyf' not in font:
        font.close()
        raise ValueError('Automatic diacritics require TrueType outlines (glyf); use a font with native characters or disable auto_diacritics.')
    glyf, hmtx, cm = font['glyf'], font['hmtx'], font.getBestCmap() or {}
    upm = font['head'].unitsPerEm
    def accent_top(reference, fallback):
        if ord(reference) in cm and 'acute' in glyf:
            return mark_bottom_from(font, glyf, cm, reference)
        if ord(fallback) in cm:
            return bounds(glyf, cm[ord(fallback)])[3] + upm * 0.04
        return upm * 0.8

    top_upper = accent_top('Ó', 'O')
    top_lower = accent_top('ó', 'o')
    added = []
    for ch, (base, mark, mode) in PL.items():
        if ord(ch) in cm or mark not in glyf or ord(base) not in cm:
            continue
        bn = cm[ord(base)]
        bx0, by0, bx1, by1 = bounds(glyf, bn)
        mx0, my0, mx1, my1 = bounds(glyf, mark)
        if mode == 'top':
            dy = (top_upper if base.isupper() else top_lower) - my0
            dx = (bx0 + bx1) / 2 - (mx0 + mx1) / 2
            if base in 'Nn' and mark == 'acute':
                dx += (bx1 - bx0) * 0.05
        else:  # ogonek below the baseline, overlapping the letter
            dy = -my1 + upm * 0.04  # top of the ogonek slightly above the baseline
            if mode == 'right':
                dx = bx1 - mx1 - (bx1 - bx0) * 0.02
            else:
                dx = (bx0 + bx1) / 2 - (mx0 + mx1) / 2 + (bx1 - bx0) * 0.12
        g = Glyph(); g.numberOfContours = -1; g.components = []
        for n, x, y in ((bn, 0, 0), (mark, round(dx), round(dy))):
            c = GlyphComponent(); c.glyphName = n; c.x, c.y = x, y; c.flags = 0x0004 if n == bn else 0
            g.components.append(c)
        name = f'uni{ord(ch):04X}'
        glyf[name] = g
        hmtx[name] = hmtx[bn]
        for t in font['cmap'].tables:
            if t.isUnicode():
                t.cmap[ord(ch)] = name
        added.append(ch)
    font.setGlyphOrder(list(glyf.glyphOrder))
    font.save(dst)
    font.close()
    return ''.join(added)


def missing_chars(path, chars):
    with TTFont(path) as font:
        cm = font.getBestCmap() or {}
    return ''.join(c for c in chars if not c.isspace() and ord(c) not in cm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--axes', default='')
    a = ap.parse_args()
    print('added:', patch_font(a.src, a.dst, a.axes) or '-')


if __name__ == '__main__':
    main()
