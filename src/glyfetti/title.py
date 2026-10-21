"""Render a whole title through one shared effect stack, without an atlas."""
import json
import math
from pathlib import Path

from fontTools.ttLib import TTFont
import numpy as np
from PIL import Image, ImageOps

from .engine import effect_padding, load_font, shaped_glyph, style_glyph
from .kerning import read_kerning
from .splatter import splatter
from .validation import validate_style

MAX_RENDER_PIXELS = 4 * 1024 * 1024


def _check_canvas(width, height, scale):
    if width * height > MAX_RENDER_PIXELS or max(width, height) / scale > 16384:
        raise ValueError('title: image is too large; shorten text, add line breaks, reduce size or supersample')


def title_image(style, base):
    """Return transparent RGBA and a report; style.preview supplies the lines."""
    st = validate_style(style)
    lines = st.get('preview', ['Level complete!', 'Score: 2 560'])
    if sum(map(len, lines)) > 10000:
        raise ValueError('title: at most 10000 text characters are supported')
    st['chars'] = ''.join(lines) or ' '
    font_path, st, font = load_font(st, Path(base))
    scale = st.get('supersample', 3)
    with TTFont(font_path) as source:
        cmap = source.getBestCmap() or {}
    chars = list(dict.fromkeys(st['chars']))
    missing = ''.join(char for char in chars if ord(char) not in cmap and char != ' ')
    supported = [char for char in chars if ord(char) in cmap and char != ' ']
    asc, desc = font.getmetrics()
    line_height = round((asc + desc) / scale * st.get('line_height', 1.15)) * scale
    options = st.get('title', {})
    alignment = options.get('align', 'center')
    padding = int(options.get('padding', 8))

    # Only shape padding is needed per letter; effect padding is added once to
    # the final union. This avoids allocating large shadow buffers per character.
    shape_style = dict(st, outline={'width': 0})
    for layer in ('side', 'shadow', 'extrude'):
        shape_style[layer] = {'enabled': False}
    glyph_padding = effect_padding(shape_style, font, supported, scale)
    glyphs = {}
    for char in supported:
        left, top, right, bottom = font.getbbox(char, anchor='ls')
        condense = st.get('condense', 1)
        estimated_width = math.ceil((right - left + 2 * glyph_padding) * condense)
        if condense != 1:
            estimated_width += 2 * glyph_padding
        _check_canvas(estimated_width, bottom - top + 2 * glyph_padding, scale)
        mask, (bx, by), advance = shaped_glyph(char, font, st, scale, glyph_padding)
        image = Image.fromarray((mask * 255).astype(np.uint8))
        bounds = image.getbbox()
        if bounds:
            cropped = mask[bounds[1]:bounds[3], bounds[0]:bounds[2]]
            glyphs[char] = (cropped, bx - bounds[0], by - bounds[1], round(advance) * scale)
        else:
            glyphs[char] = (None, 0, 0, round(advance) * scale)
    kernings = read_kerning(font_path, supported + [' '], st['size'], st.get('condense', 1),
                            st.get('variation'), st.get('kerning_script', 'latn')) if st.get('kerning', True) else []
    pairs = {(pair['first'], pair['second']): pair['amount'] * scale for pair in kernings}
    space = round(font.getlength(' ') / scale * st.get('condense', 1) + st.get('tracking', 0)) * scale
    layouts = []
    for index, text in enumerate(lines):
        cursor = 0
        previous = None
        placements = []
        for char in text:
            if previous is not None:
                cursor += pairs.get((ord(previous), ord(char)), 0)
            if char in glyphs:
                mask, bx, by, advance = glyphs[char]
                if mask is not None:
                    placements.append((mask, round(cursor - bx), round(asc + index * line_height - by)))
                cursor += advance
            else:
                cursor += space
            previous = char if char in glyphs or char == ' ' else None
        if placements:
            left = min(x for mask, x, y in placements)
            right = max(x + mask.shape[1] for mask, x, y in placements)
            layouts.append((placements, left, right - left))
    if not layouts:
        raise ValueError(f'title: no supported visible characters to render{": " + missing if missing else ""}')
    width = max(layout[2] for layout in layouts)
    fraction = {'left': 0, 'center': .5, 'right': 1}[alignment]
    placements = []
    for layout, left, line_width in layouts:
        offset = round((width - line_width) * fraction) - left
        placements.extend((mask, x + offset, y) for mask, x, y in layout)
    top = min(y for mask, x, y in placements)
    bottom = max(y + mask.shape[0] for mask, x, y in placements)
    effect_pad = effect_padding(st, font, supported, scale)
    canvas_width, canvas_height = width + 2 * effect_pad, bottom - top + 2 * effect_pad
    _check_canvas(canvas_width, canvas_height, scale)
    canvas = np.zeros((canvas_height, canvas_width), dtype=np.float32)
    for mask, x, y in placements:
        x, y = x + effect_pad, y - top + effect_pad
        h, w = mask.shape
        region = canvas[y:y + h, x:x + w]
        np.maximum(region, mask, out=region)
    # A title has one continuous gradient and highlight across the entire mask.
    st['_line_top'], st['_line_bottom'] = effect_pad, canvas_height - effect_pad - 1
    rgba = style_glyph(canvas, st, scale)
    image = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), 'RGBA')
    image = image.resize((max(1, math.ceil(image.width / scale)), max(1, math.ceil(image.height / scale))), Image.Resampling.LANCZOS)
    if image.getbbox() is None:
        raise ValueError('title: no visible pixels to export')
    if options.get('splatter'):
        image = splatter(image, options['splatter'])
    bounds = image.getbbox()
    image = ImageOps.expand(image.crop(bounds), border=padding, fill=(0, 0, 0, 0))
    return image, {'name': st['name'], 'size': image.size, 'glyphs': len(glyphs),
                   'kernings': len(kernings), 'skipped': missing, 'lines': len(lines)}


def build_title(style_path, output=None, text=None, align=None):
    style_path = Path(style_path)
    st = validate_style(json.loads(style_path.read_text('utf-8')))
    if text is not None:
        st['preview'] = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if align is not None:
        st.setdefault('title', {})['align'] = align
    if output is not None and Path(output).suffix.lower() != '.png':
        raise ValueError('title: output must use the .png extension')
    image, report = title_image(st, style_path.parent)
    output = Path(output) if output else style_path.parent / 'out' / f"{report['name']}_title.png"
    if output.suffix.lower() != '.png':
        raise ValueError('title: output must use the .png extension')
    background = st.get('preview_bg', '#ffffff')
    preview = Image.new('RGBA', image.size, (0, 0, 0, 0) if background == 'transparent' else background)
    preview.alpha_composite(image)
    preview_path = output.with_name(output.stem + '_preview.png')
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    preview.save(preview_path)
    return {**report, 'out': output, 'preview': preview_path}
