"""Glyfetti rendering engine: styled bitmap font atlases (PNG + BMFont .fnt + JSON).

Every glyph goes through the same layer stack (bottom-up):
  shadow -> extrude -> outline -> side -> fill -> bevel -> gloss
All parameters live in a style JSON file (see docs/STYLE_REFERENCE.md).
"""
import hashlib
import json, math
import os
import tempfile
import warnings
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from .validation import DATA_DIR, validate_style
from .packing import pack_atlas, shelf_pack
from .kerning import read_kerning


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


def resolve_font(st, base):
    """Find the font file and, if needed, auto-compose missing Polish diacritics."""
    cands = [base / st['font'], base.parent / 'fonts' / Path(st['font']).name, FONTS_DIR / Path(st['font']).name]
    path = next((c for c in cands if c.exists()), None)
    if path is None:
        raise FileNotFoundError(f"font not found: {st['font']}")
    if st.get('variation'):
        from fontTools.ttLib import TTFont
        with TTFont(path) as source:
            if 'fvar' not in source:
                raise ValueError('variation: font has no variable axes')
            axes = source['fvar'].axes
            variation = st['variation']
            if isinstance(variation, list):
                if len(variation) != len(axes):
                    raise ValueError('variation: number of values must match the font axes')
                variation = dict(zip((a.axisTag for a in axes), variation))
            if set(variation) - {a.axisTag for a in axes}:
                raise ValueError('variation: unknown font axis')
            for axis in axes:
                value = variation.get(axis.axisTag, axis.defaultValue)
                if not axis.minValue <= value <= axis.maxValue:
                    raise ValueError(f'variation.{axis.axisTag}: must be between {axis.minValue} and {axis.maxValue}')
            st = dict(st, variation=variation)
    if st.get('auto_diacritics', True):
        from .patch import missing_chars, patch_font
        from .patch import PL
        if any(c in PL for c in missing_chars(path, st['chars'])):
            from fontTools.ttLib import TTFont
            with TTFont(path) as source:
                if 'glyf' not in source:
                    warnings.warn('Automatic diacritics unavailable for CFF outlines; missing characters will be reported.', stacklevel=2)
                    return path, st
            cache = Path.home() / '.cache' / 'glyfetti'
            cache.mkdir(parents=True, exist_ok=True)
            variation = st.get('variation') or {}
            if isinstance(variation, list):
                with TTFont(path) as source:
                    axes = source['fvar'].axes if 'fvar' in source else []
                    if len(variation) != len(axes):
                        raise ValueError('variation: number of values must match the font axes')
                    variation = dict(zip((a.axisTag for a in axes), variation))
            digest = hashlib.sha256(path.read_bytes() + json.dumps(variation, sort_keys=True).encode() + b'patch-v2').hexdigest()
            out = cache / f'{digest}-patched.ttf'
            if not out.exists():
                fd, temporary = tempfile.mkstemp(suffix='.ttf', dir=cache)
                os.close(fd)
                try:
                    patch_font(str(path), temporary, variation)
                    os.replace(temporary, out)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            st = dict(st); st.pop('variation', None)
            return out, st
    return path, st


def prepare_style(style, base, text=None):
    """Validate a style, merge preview text into chars and pin an absolute font path."""
    raw = validate_style(style)
    if text is not None:
        raw['preview'] = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    raw['chars'] = ''.join(dict.fromkeys(raw['chars'] + ''.join(raw.get('preview', []))))
    raw = validate_style(raw)
    font_path, _ = resolve_font(dict(raw, auto_diacritics=False), Path(base))
    raw['font'] = str(font_path.resolve())
    return raw


FONTS_DIR = DATA_DIR / 'fonts'


def effect_padding(st, font, chars, scale):
    """Conservative padding for the complete effect stack, in final pixels."""
    def layer(name):
        value = st.get(name, {})
        return value if value.get('enabled', True) else {}

    side, shadow, extrude = (layer(k) for k in ('side', 'shadow', 'extrude'))
    extent = st['outline']['width'] + st.get('embolden', 0)
    extent += max(abs(side.get('dx', 0)), side.get('depth', 0))
    extent += max(
        abs(shadow.get('dx', 0)), abs(shadow.get('dy', 0)), 0
    ) + 4 * shadow.get('blur', 0)
    extent += extrude.get('depth', 0) + 4 * extrude.get('blur', 0)
    jitter = st.get('jitter') or {}
    if jitter.get('rotate', 0):
        radius = max((max(abs(v) for v in font.getbbox(c, anchor='ls')) / scale for c in chars), default=0)
        extent += 2 * radius * math.sin(math.radians(jitter['rotate']) / 2)
    return math.ceil((extent + 4) * scale)


def load_font(st, base):
    """Resolve, patch and configure a font identically for every output mode."""
    font_path, st = resolve_font(st, base)
    S = st.get('supersample', 3)
    size = st['size']
    font = ImageFont.truetype(str(font_path), size * S)
    var = st.get('variation')
    if var:
        if isinstance(var, dict):  # np. {"wght": 800, "wdth": 75}
            from fontTools.ttLib import TTFont
            with TTFont(str(font_path)) as source:
                if 'fvar' not in source:
                    raise ValueError('variation: font has no variable axes')
                axes = source['fvar'].axes
            unknown = set(var) - {a.axisTag for a in axes}
            if unknown:
                raise ValueError(f'variation: unknown axes {sorted(unknown)}')
            var = [var.get(a.axisTag, a.defaultValue) for a in axes]
        font.set_variation_by_axes(var)
    return font_path, st, font


def shaped_glyph(ch, font, st, S, pad):
    """Plain glyph mask, local baseline and advance, before colored effects."""
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
    adv = font.getlength(ch) / S * st.get('condense', 1.0) + st.get('embolden', 0) * 2 + st.get('tracking', 0)
    return m, (bx, by), adv


def build(style_path, out_dir=None, preview_only=False, inspect=False):
    st = validate_style(json.loads(Path(style_path).read_text(encoding='utf-8')))
    maximum = st.get('max_atlas_size', 8192)
    if st.get('atlas_width', 1024) > maximum:
        raise ValueError('atlas_width: exceeds max_atlas_size')
    base = Path(style_path).parent
    font_path, st, font = load_font(st, base)
    S = st.get('supersample', 3)
    size = st['size']
    asc, desc = font.getmetrics()
    st['_line_top'] = 0
    st['_line_bottom'] = asc
    if preview_only:
        st['chars'] = ''.join(st.get('preview', ['Level complete!', 'Score: 2 560']))
    chars = list(dict.fromkeys(st['chars'].replace('\n', '')))
    if ' ' in chars:
        chars.remove(' ')
    from fontTools.ttLib import TTFont as _TT
    with _TT(str(font_path)) as source:
        _cm = source.getBestCmap() or {}
    skipped = ''.join(c for c in chars if ord(c) not in _cm)
    chars = [c for c in chars if ord(c) in _cm]
    pad = effect_padding(st, font, chars, S)

    glyphs = []
    clipped_glyphs = []
    for ch in chars:
        m, (bx, by), adv = shaped_glyph(ch, font, st, S, pad)
        st['_line_top'] = by - asc
        st['_line_bottom'] = by
        rgba = style_glyph(m, st, S)
        if inspect:
            # Inspect BEFORE cropping the transparent padding: final glyph rectangles
            # are intentionally tight and cannot reveal render-buffer clipping.
            alpha = rgba[..., 3]
            if (alpha[0].max() > 1 / 255 or alpha[-1].max() > 1 / 255
                    or alpha[:, 0].max() > 1 / 255 or alpha[:, -1].max() > 1 / 255):
                clipped_glyphs.append(ch)
        img = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), 'RGBA')
        img = img.resize((max(1, round(img.width / S)), max(1, round(img.height / S))), Image.LANCZOS)
        bb = img.getbbox() or (0, 0, 1, 1)
        img = img.crop(bb)
        # baseline and left edge position after scaling and cropping
        ox, oy = bx / S - bb[0], by / S - bb[1]
        glyphs.append(dict(ch=ch, img=img, ox=ox, oy=oy, adv=adv))

    pos, H, packing = pack_atlas([g['img'].size for g in glyphs], st.get('atlas_width', 1024), 2, maximum, st.get('atlas_packing', 'maxrects'))
    kernings = read_kerning(font_path, chars + [' '], size, st.get('condense', 1), st.get('variation'), st.get('kerning_script', 'latn')) if st.get('kerning', True) else []
    pair_offsets = {(pair['first'], pair['second']): pair['amount'] for pair in kernings}
    W = st.get('atlas_width', 1024)
    atlas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    base_y = round(asc / S + st['outline']['width'])
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

    lines.append(f'kernings count={len(kernings)}')
    lines.extend(f"kerning first={pair['first']} second={pair['second']} amount={pair['amount']}" for pair in kernings)

    out = Path(out_dir) if out_dir else base / 'out'
    out.mkdir(parents=True, exist_ok=True)
    atlas.save(out / f'{name}.png')
    (out / f'{name}.fnt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # JSON dla importera Unity (TextMeshPro)
    jd = {'name': name, 'size': size, 'lineHeight': line_h, 'baseline': base_y, 'scaleW': W, 'scaleH': H, 'kernings': kernings,
          'chars': [{'id': 32, 'x': 0, 'y': 0, 'w': 0, 'h': 0, 'xo': 0, 'yo': 0, 'xa': space_adv}] +
                   [{'id': ord(g['ch']), 'x': g['x'], 'y': g['y'], 'w': g['img'].size[0], 'h': g['img'].size[1],
                     'xo': g['xoff'], 'yo': g['yoff'], 'xa': round(g['adv'])} for g in glyphs]}
    (out / f'{name}.json').write_text(json.dumps(jd, ensure_ascii=False), encoding='utf-8')

    if not inspect:
        # preview: assemble text from the atlas using the metrics (tests them)
        gm = {g['ch']: g for g in glyphs}
        sample = st.get('preview', ['Level complete!', 'Score: 2 560'])
        placements = []
        left = top = 0
        right, bottom = 0, line_h * len(sample)
        for i, text in enumerate(sample):
            cursor = 0
            previous = None
            for char in text:
                if previous is not None:
                    cursor += pair_offsets.get((ord(previous), ord(char)), 0)
                if char in gm:
                    glyph = gm[char]
                    x, y = cursor + glyph['xoff'], i * line_h + glyph['yoff']
                    placements.append((glyph['img'], x, y))
                    left, top = min(left, x), min(top, y)
                    right, bottom = max(right, x + glyph['img'].width), max(bottom, y + glyph['img'].height)
                    cursor += round(glyph['adv'])
                else:
                    cursor += space_adv
                previous = char if char in gm or char == ' ' else None
            left, right = min(left, cursor), max(right, cursor)
        pw, ph = right - left + 80, bottom - top + 60
        if pw * ph > 64 * 1024 * 1024:
            raise ValueError('preview: image exceeds 64 megapixels; shorten preview text or reduce size')
        bgc = st.get('preview_bg', '#ffffff')
        bg = (0, 0, 0, 0) if bgc == 'transparent' else tuple(int(bgc.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        prev = Image.new('RGBA', (pw, ph), bg)
        for image, x, y in placements:
            prev.alpha_composite(image, (x - left + 40, y - top + 30))
        prev.save(out / f'{name}_preview.png')

        sheet = Image.new('RGBA', (W, H), (255, 255, 255, 255))
        sheet.alpha_composite(atlas)
        sheet.save(out / f'{name}_atlas_on_white.png')
    return {'glyphs': len(glyphs), 'atlas': (W, H), 'out': out, 'name': name, 'skipped': skipped, 'kernings': len(kernings), 'packing': packing,
            'occupancy': sum(g['img'].width * g['img'].height for g in glyphs) / (W * H),
            'clipped_glyphs': clipped_glyphs if inspect else []}


