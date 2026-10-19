"""Extract an editable Glyfetti palette from an isolated text reference image.

This is a deterministic color/edge estimator, not OCR or font identification.
All pixels stay local; neither the source image nor its bytes are saved.
"""
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from scipy import ndimage as ndi

from .validation import validate_style


MAX_REFERENCE_BYTES = 4 * 1024 * 1024
MAX_REFERENCE_PIXELS = 2_500_000


def _hex(rgb):
    values = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return '#' + ''.join(f'{int(value):02X}' for value in values)


def _darken(color, ratio):
    rgb = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)
    return _hex(rgb * ratio)


def _foreground(rgb, alpha):
    """Prefer real transparency; otherwise remove a nearly uniform border."""
    height, width = alpha.shape
    border_alpha = np.concatenate((alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]))
    if np.mean(border_alpha < 200) > .75:
        return alpha >= 128, 'alpha', None

    border = np.concatenate((rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]))
    background = np.median(border, axis=0)
    deviations = np.max(np.abs(border.astype(np.int16) - background), axis=1)
    if np.mean(deviations > 40) > .20:
        raise ValueError('Reference image needs a transparent or mostly uniform background; crop the lettering first.')

    difference = np.max(np.abs(rgb.astype(np.int16) - background), axis=2)
    similar = difference <= max(32, float(np.percentile(deviations, 85)) + 16)
    seeds = np.zeros((height, width), dtype=bool)
    seeds[0] = similar[0]
    seeds[-1] = similar[-1]
    seeds[:, 0] = similar[:, 0]
    seeds[:, -1] = similar[:, -1]
    # Connected background removal keeps enclosed holes of A, O, etc.
    background_mask = ndi.binary_propagation(seeds, mask=similar)
    return ~background_mask, 'background', _hex(background)


def analyze_reference(image_bytes, base_style):
    """Return {'style': valid raw style, 'analysis': diagnostics} from PNG/JPEG bytes.

    Typical inputs are game-title crops on transparent or simple backgrounds.
    The existing font, preview text and geometry remain unchanged.
    """
    if not isinstance(image_bytes, bytes) or not 0 < len(image_bytes) <= MAX_REFERENCE_BYTES:
        raise ValueError('Reference PNG/JPEG must be between 1 byte and 4 MiB.')
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            if source.format not in ('PNG', 'JPEG'):
                raise ValueError('Only PNG and JPEG reference images are supported.')
            width, height = source.size
            if width < 16 or height < 16 or width * height > MAX_REFERENCE_PIXELS:
                raise ValueError('Reference dimensions must be at least 16×16 and at most 2.5 megapixels.')
            pixels = np.asarray(ImageOps.exif_transpose(source).convert('RGBA'))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError('Could not read reference PNG/JPEG image.') from error

    style = validate_style(base_style)
    rgb = pixels[:, :, :3]
    alpha = pixels[:, :, 3]
    mask, method, background_color = _foreground(rgb, alpha)

    # Ignore isolated JPEG specks, but preserve dots/accents in actual lettering.
    labels, count = ndi.label(mask)
    if count:
        sizes = np.bincount(labels.ravel())
        mask &= (sizes[labels] >= 3) & (labels != 0)
    if mask.sum() < 64 or mask.mean() < .001:
        raise ValueError('No clear lettering found. Use a tighter crop with sufficient contrast.')
    if mask.mean() > .85:
        raise ValueError('Foreground covers almost the entire image; use an isolated title image.')

    y, x = np.where(mask)
    y0, y1 = int(y.min()), int(y.max())
    distance = ndi.distance_transform_edt(mask)
    occupied = distance[mask]
    cutoff = max(2.5, float(np.percentile(occupied, 70)) * .65)
    core = mask & (distance >= cutoff)
    if core.sum() < 24:
        core = mask & (distance >= 1.5)
    if core.sum() < 24:
        raise ValueError('Letter strokes are too thin to estimate the fill palette.')

    core_color = np.median(rgb[core], axis=0)
    ring = mask & (distance <= 2.2)
    edge_color = np.median(rgb[ring], axis=0)
    contrast = float(np.linalg.norm(core_color - edge_color))
    has_outline = contrast >= 45

    colors = []
    for fraction in (.1, .5, .9):
        target_y = y0 + fraction * (y1 - y0)
        band = max(2, round((y1 - y0 + 1) * .09))
        rows = np.abs(np.arange(height)[:, None] - target_y) <= band
        sample = rgb[core & rows]
        if sample.shape[0] < 12:
            sample = rgb[core]
        colors.append(_hex(np.median(sample, axis=0)))

    style['fill']['stops'] = [[0, colors[0]], [0.5, colors[1]], [1, colors[2]]]
    style['fill']['gradient_space'] = 'glyph'
    style['outline']['color'] = _hex(edge_color) if has_outline else _darken(colors[-1], .35)

    if has_outline:
        # Measure outer edge-like pixels in reference pixels; scale to font size.
        edge_dist = np.linalg.norm(rgb.astype(np.float32) - edge_color, axis=2)
        core_dist = np.linalg.norm(rgb.astype(np.float32) - core_color, axis=2)
        outline_pixels = mask & (edge_dist < core_dist * .75) & (distance <= (y1 - y0 + 1) * .18)
        thickness = float(np.percentile(distance[outline_pixels], 70)) if outline_pixels.sum() > 12 else 2.0
        style['outline']['width'] = round(float(np.clip(thickness * style['size'] / max(y1 - y0 + 1, 12), 1, 20)), 2)
    else:
        style['outline']['width'] = 0

    # Preserve the selected preset's geometry; update its existing tint layers.
    if isinstance(style.get('side'), dict):
        style['side']['color_top'] = _darken(colors[-1], .8)
        style['side']['color_bottom'] = _darken(colors[-1], .48)
    if isinstance(style.get('shadow'), dict):
        style['shadow']['color'] = _darken(style['outline']['color'], .6)
    style = validate_style(style)
    return {
        'style': style,
        'analysis': {
            'image_size': [width, height],
            'segmentation': method,
            'background': background_color or 'transparent',
            'fill_colors': colors,
            'outline_detected': has_outline,
            'outline_width': style['outline']['width'],
            'warning': 'Estimated colors and outline only; font, extrusion, gloss and shadow geometry retain the selected style.',
        },
    }
