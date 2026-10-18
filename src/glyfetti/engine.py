"""Glyfetti rendering engine: styled bitmap font atlases (PNG + BMFont .fnt + JSON).

Every glyph goes through the same layer stack (bottom-up):
  shadow -> extrude -> outline -> side -> fill -> bevel -> gloss
All parameters live in a style JSON file (see docs/STYLE_REFERENCE.md).
"""
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi


def hex2rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def over(dst, rgb, alpha):
    """Alpha-composite warstwy (rgb HxWx3, alpha HxW) na dst (HxWx4, premultiplied=False)."""
    a = alpha[..., None]
    da = dst[..., 3:4]
    out_a = a + da * (1 - a)
    safe = np.where(out_a > 1e-6, out_a, 1)
    dst[..., :3] = (rgb * a + dst[..., :3] * da * (1 - a)) / safe
    dst[..., 3:4] = out_a
    return dst


def grow(mask, r):
    """Grow a mask by r px with an anti-aliased edge (via distance transform)."""
    if r <= 0:
        return mask
    d = ndi.distance_transform_edt(mask < 0.5)
    return np.maximum(mask, np.clip(r + 0.5 - d, 0, 1))


def shift(a, dx, dy):
    return ndi.shift(a, (dy, dx), order=1, mode='constant')


def render_glyph(ch, font, S, pad):
    """Return the 0..1 glyph mask (at scale S), baseline position and bbox."""
    l, t, r, b = font.getbbox(ch, anchor='ls')
    w, h = r - l + 2 * pad, b - t + 2 * pad
    img = Image.new('L', (max(w, 1), max(h, 1)), 0)
    ImageDraw.Draw(img).text((pad - l, pad - t), ch, font=font, fill=255, anchor='ls')
    return np.asarray(img, dtype=np.float32) / 255.0, (pad - l, pad - t), (l, t, r, b)


def style_glyph(m, st, S):
    """Apply the effect stack to mask m (supersampled by S). Returns float RGBA."""
    H, W = m.shape
    out = np.zeros((H, W, 4), np.float32)
    o = st['outline']['width'] * S
    # letter side (3D thickness) – copies of the shape shifted down/right
    sd = st.get('side')
    side_mask = None
    if sd and sd.get('enabled', True):
        depth = int(round(sd['depth'] * S))
        side_mask = np.zeros_like(m)
        for k in range(1, depth + 1):
            side_mask = np.maximum(side_mask, shift(m, sd.get('dx', 0) * S * k / depth, k))
    body = m if side_mask is None else np.maximum(m, side_mask)
    outline_mask = grow(body, o)

    # 1) shadow
    sh = st.get('shadow')
    if sh and sh.get('enabled', True):
        a = shift(outline_mask, sh['dx'] * S, sh['dy'] * S)
        if sh.get('blur', 0) > 0:
            a = ndi.gaussian_filter(a, sh['blur'] * S)
        over(out, hex2rgb(sh['color']), a * sh['opacity'])

    # 2) extrude (hard base under the outline)
    ex = st.get('extrude')
    if ex and ex.get('enabled', True):
        depth = int(round(ex['depth'] * S))
        acc = np.zeros_like(outline_mask)
        for k in range(1, depth + 1):
            acc = np.maximum(acc, shift(outline_mask, 0, k))
        if ex.get('blur', 0) > 0:
            acc = ndi.gaussian_filter(acc, ex['blur'] * S)
        over(out, hex2rgb(ex['color']), acc * ex.get('opacity', 1.0))

    # 3) obrys
    over(out, hex2rgb(st['outline']['color']), outline_mask)

    # 3b) side – darker gradient under the outline
    if side_mask is not None:
        ys_ = np.where(body.max(axis=1) > 0.5)[0]
        sy0, sy1 = (ys_.min(), ys_.max()) if len(ys_) else (0, H - 1)
        ts = np.clip((np.arange(H, dtype=np.float32) - sy0) / max(sy1 - sy0, 1), 0, 1)[:, None]
        c0, c1 = hex2rgb(sd['color_top']), hex2rgb(sd['color_bottom'])
        srgb = (c0 + (c1 - c0) * ts[..., None]) * np.ones((1, W, 1))
        over(out, srgb, side_mask)

    # 4) gradient fill (relative to the glyph bbox or the whole line)
    ys = np.where(m.max(axis=1) > 0.5)[0]
    y0, y1 = (ys.min(), ys.max()) if len(ys) else (0, H - 1)
    if st['fill'].get('gradient_space') == 'line':
        y0, y1 = st['_line_top'], st['_line_bottom']
    t = np.clip((np.arange(H, dtype=np.float32) - y0) / max(y1 - y0, 1), 0, 1)[:, None]
    stops = st['fill']['stops']
    pos = np.array([s[0] for s in stops], np.float32)
    cols = np.stack([hex2rgb(s[1]) for s in stops])
    rgb = np.stack([np.interp(t, pos, cols[:, c]) for c in range(3)], -1) * np.ones((1, W, 1))
    inner = m.copy()

    # 5) bevel – lighting from a height map (inner distance field)
    bv = st.get('bevel')
    if bv and bv.get('enabled', True):
        d = ndi.distance_transform_edt(m > 0.5)
        hgt = np.clip(d / (bv['size'] * S), 0, 1)
        hgt = 1 - (1 - hgt) ** 2                       # rounded profile
        hgt = ndi.gaussian_filter(hgt, bv.get('soften', 1.0) * S)
        gy, gx = np.gradient(hgt)
        ang = math.radians(bv['light_angle'])         # 90 = from the top
        lx, ly = math.cos(ang), -math.sin(ang)
        shade = -(gx * lx + gy * ly) * (bv['size'] * S)   # >0 = lit
        shade = np.clip(shade, -1, 1)
        hi = np.clip(shade, 0, 1)[..., None] * bv['highlight_strength']
        lo = np.clip(-shade, 0, 1)[..., None] * bv['shadow_strength']
        rgb = rgb + (hex2rgb(bv['highlight_color']) - rgb) * hi
        rgb = rgb + (hex2rgb(bv['shadow_color']) - rgb) * lo

    # 6) gloss – soft highlight in the upper part of the letter
    gl = st.get('gloss')
    if gl and gl.get('enabled', True):
        er = ndi.distance_transform_edt(m > 0.5) > gl['inset'] * S
        band = np.clip(1 - (np.arange(H) - y0) / max((y1 - y0) * gl['height'], 1), 0, 1)[:, None]
        g = ndi.gaussian_filter(er * band, gl['blur'] * S) * gl['opacity']
        rgb = rgb + (hex2rgb(gl['color']) - rgb) * g[..., None]

    over(out, np.clip(rgb, 0, 1), inner)
    return out


def shelf_pack(sizes, width, pad):
    x = y = row_h = 0
    pos = []
    for w, h in sizes:
        if x + w + pad > width:
            x, y, row_h = 0, y + row_h + pad, 0
        pos.append((x + pad, y + pad))
        x += w + pad
        row_h = max(row_h, h)
    height = y + row_h + 2 * pad
    return pos, 1 << math.ceil(math.log2(max(height, 1)))


def resolve_font(st, base):
    """Find the font file and, if needed, auto-compose missing Polish diacritics."""
    cands = [base / st['font'], base.parent / 'fonts' / Path(st['font']).name, FONTS_DIR / Path(st['font']).name]
    path = next((c for c in cands if c.exists()), None)
    if path is None:
        raise FileNotFoundError(f"font not found: {st['font']}")
    if st.get('auto_diacritics', True):
        from .patch import missing_chars, patch_font
        if missing_chars(path, st['chars']):
            cache = Path.home() / '.cache' / 'glyfetti'
            cache.mkdir(parents=True, exist_ok=True)
            tag = '' if not isinstance(st.get('variation'), dict) else '_' + '_'.join(f'{k}{v}' for k, v in sorted(st['variation'].items()))
            out = cache / f'{path.stem}{tag}-patched.ttf'
            if not out.exists():
                patch_font(str(path), str(out), st.get('variation') or '')
            if 'fvar' not in __import__('fontTools.ttLib', fromlist=['TTFont']).TTFont(str(out)):
                st = dict(st); st.pop('variation', None)
            return out, st
    return path, st


FONTS_DIR = Path(__file__).resolve().parents[2] / 'fonts'


def build(style_path, out_dir=None, preview_only=False):
    st = json.loads(Path(style_path).read_text(encoding='utf-8'))
    base = Path(style_path).parent
    font_path, st = resolve_font(st, base)
    S = st.get('supersample', 3)
    size = st['size']
    font = ImageFont.truetype(str(font_path), size * S)
    var = st.get('variation')
    if var:
        if isinstance(var, dict):  # np. {"wght": 800, "wdth": 75}
            from fontTools.ttLib import TTFont
            axes = TTFont(str(font_path))['fvar'].axes
            var = [var.get(a.axisTag, a.defaultValue) for a in axes]
        font.set_variation_by_axes(var)
    asc, desc = font.getmetrics()
    st['_line_top'] = 0
    st['_line_bottom'] = asc
    eff = st['outline']['width'] + max(st.get('extrude', {}).get('depth', 0),
                                       st.get('shadow', {}).get('dy', 0) + st.get('shadow', {}).get('blur', 0) * 3)
    pad = int(math.ceil((eff + 4) * S))
    if preview_only:
        st['chars'] = ''.join(st.get('preview', []))
    chars = list(dict.fromkeys(st['chars'].replace('\n', '')))
    if ' ' in chars:
        chars.remove(' ')
    from fontTools.ttLib import TTFont as _TT
    _cm = _TT(str(font_path)).getBestCmap()
    skipped = ''.join(c for c in chars if ord(c) not in _cm)
    chars = [c for c in chars if ord(c) in _cm]

    glyphs = []
    for ch in chars:
        m, (bx, by), bbox = render_glyph(ch, font, S, pad)
        cond = st.get('condense', 1.0)
        if cond != 1.0:  # horizontal condense from the left margin
            H0, W0 = m.shape
            nw = max(1, round(W0 * cond))
            m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((nw, H0), Image.LANCZOS), np.float32) / 255.0
            bx = bx * cond
            bbox = (bbox[0] * cond, bbox[1], bbox[2] * cond, bbox[3])
            # pad so effects still fit
            m = np.pad(m, ((0, 0), (pad, pad)))
            bx += pad
        if st.get('embolden', 0) > 0:
            m = grow(m, st['embolden'] * S)
        jit = st.get('jitter')
        if jit:  # deterministic "bouncy" letters: rotation + vertical offset
            import zlib, random
            rnd = random.Random(zlib.crc32(ch.encode()) ^ jit.get('seed', 0))
            ang = rnd.uniform(-1, 1) * jit.get('rotate', 0)
            dy = rnd.uniform(-1, 1) * jit.get('y', 0) * S
            cx = bx + (bbox[2] - bbox[0]) / 2
            im = Image.fromarray((m * 255).astype(np.uint8)).rotate(ang, Image.BICUBIC, center=(cx, by))
            m = np.asarray(im, np.float32) / 255.0
            by = by + dy
        rgba = style_glyph(m, st, S)
        img = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), 'RGBA')
        img = img.resize((max(1, round(img.width / S)), max(1, round(img.height / S))), Image.LANCZOS)
        bb = img.getbbox() or (0, 0, 1, 1)
        img = img.crop(bb)
        # baseline and left edge position after scaling and cropping
        ox, oy = bx / S - bb[0], by / S - bb[1]
        adv = font.getlength(ch) / S * st.get('condense', 1.0) + st.get('embolden', 0) * 2 + st.get('tracking', 0)
        glyphs.append(dict(ch=ch, img=img, ox=ox, oy=oy, adv=adv))

    pos, H = shelf_pack([g['img'].size for g in glyphs], st.get('atlas_width', 1024), 2)
    W = st.get('atlas_width', 1024)
    atlas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    base_y = round(asc / S) + st['outline']['width']
    line_h = round((asc + desc) / S * st.get('line_height', 1.15))
    name = st['name']
    lines = [f'info face="{name}" size={size} bold=0 italic=0 charset="" unicode=1 stretchH=100 smooth=1 aa=1 padding=0,0,0,0 spacing=2,2',
             f'common lineHeight={line_h} base={base_y} scaleW={W} scaleH={H} pages=1 packed=0',
             f'page id=0 file="{name}.png"', f'chars count={len(glyphs) + 1}']
    space_adv = round(font.getlength(' ') / S * st.get('condense', 1.0) + st.get('tracking', 0))
    lines.append(f'char id=32 x=0 y=0 width=0 height=0 xoffset=0 yoffset=0 xadvance={space_adv} page=0 chnl=15')
    for g, (x, y) in zip(glyphs, pos):
        atlas.paste(g['img'], (x, y))
        w, h = g['img'].size
        g.update(x=x, y=y, xoff=round(-g['ox']), yoff=round(base_y - g['oy']))
        lines.append(f"char id={ord(g['ch'])} x={x} y={y} width={w} height={h} "
                     f"xoffset={g['xoff']} yoffset={g['yoff']} xadvance={round(g['adv'])} page=0 chnl=15")

    out = Path(out_dir) if out_dir else base / 'out'
    out.mkdir(parents=True, exist_ok=True)
    atlas.save(out / f'{name}.png')
    (out / f'{name}.fnt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # JSON dla importera Unity (TextMeshPro)
    jd = {'name': name, 'size': size, 'lineHeight': line_h, 'baseline': base_y, 'scaleW': W, 'scaleH': H,
          'chars': [{'id': 32, 'x': 0, 'y': 0, 'w': 0, 'h': 0, 'xo': 0, 'yo': 0, 'xa': space_adv}] +
                   [{'id': ord(g['ch']), 'x': g['x'], 'y': g['y'], 'w': g['img'].size[0], 'h': g['img'].size[1],
                     'xo': g['xoff'], 'yo': g['yoff'], 'xa': round(g['adv'])} for g in glyphs]}
    (out / f'{name}.json').write_text(json.dumps(jd, ensure_ascii=False), encoding='utf-8')

    # preview: assemble text from the atlas using the metrics (tests them)
    gm = {g['ch']: g for g in glyphs}
    sample = st.get('preview', ['Level complete!', 'Score: 2 560'])
    pw = max(sum(round(gm[c]['adv']) if c in gm else space_adv for c in s) for s in sample) + 80
    bgc = st.get('preview_bg', '#ffffff')
    bg = (0, 0, 0, 0) if bgc == 'transparent' else tuple(int(bgc.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    prev = Image.new('RGBA', (pw, line_h * len(sample) + 60), bg)
    for i, s in enumerate(sample):
        cx, cy = 40, 30 + i * line_h
        for c in s:
            if c in gm:
                g = gm[c]
                prev.alpha_composite(g['img'], (cx + g['xoff'], cy + g['yoff']))
                cx += round(g['adv'])
            else:
                cx += space_adv
    prev.save(out / f'{name}_preview.png')

    sheet = Image.new('RGBA', (W, H), (255, 255, 255, 255))
    sheet.alpha_composite(atlas)
    sheet.save(out / f'{name}_atlas_on_white.png')
    return {'glyphs': len(glyphs), 'atlas': (W, H), 'out': out, 'name': name, 'skipped': skipped}


