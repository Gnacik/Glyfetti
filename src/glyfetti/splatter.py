"""Paint splatters around a rendered title."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

DEFAULT_COLORS = ['#FF2E88', '#1E90FF', '#FFD21F', '#7B2FF7', '#00C2A8', '#FF7A1A']


def blot(rng, size, color):
    """One splat: irregular core, tapered rays with droplets, fine spray and drips."""
    s = size * 3
    mask = Image.new('L', (s, s))
    d = ImageDraw.Draw(mask)
    c = s / 2
    for _ in range(rng.integers(6, 12)):
        ox, oy = rng.normal(0, 0.12 * size, 2)
        r = rng.uniform(0.18, 0.34) * size
        d.ellipse([c + ox - r, c + oy - r * rng.uniform(0.7, 1), c + ox + r, c + oy + r], 255)
    for _ in range(rng.integers(8, 18)):
        ang = rng.uniform(0, 2 * math.pi)
        length, w = rng.uniform(0.45, 1.05) * size, rng.uniform(0.04, 0.1) * size
        ca, sa = math.cos(ang), math.sin(ang)
        tip = (c + ca * length, c + sa * length)
        d.polygon([(c - sa * w, c + ca * w), (c + sa * w, c - ca * w), tip], 255)
        r = w * rng.uniform(0.6, 1.1)
        d.ellipse([tip[0] - r, tip[1] - r, tip[0] + r, tip[1] + r], 255)
    for _ in range(rng.integers(25, 60)):
        ang, dist = rng.uniform(0, 2 * math.pi), size * (0.5 + rng.exponential(0.35))
        r = rng.uniform(0.008, 0.035) * size
        x, y = c + math.cos(ang) * dist, c + math.sin(ang) * dist
        d.ellipse([x - r, y - r, x + r, y + r], 255)
    for _ in range(rng.integers(0, 3)):
        x = c + rng.uniform(-0.25, 0.25) * size
        length, w = rng.uniform(0.4, 1.0) * size, rng.uniform(0.025, 0.05) * size
        d.polygon([(x - w, c), (x + w, c), (x + w * 0.7, c + length), (x - w * 0.7, c + length)], 255)
        d.ellipse([x - w * 1.1, c + length - w, x + w * 1.1, c + length + w * 1.2], 255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(size * 0.02, 0.5)))
    mask = mask.point(lambda v: 255 if v > 110 else 0).filter(ImageFilter.GaussianBlur(0.7))
    out = Image.new('RGBA', mask.size, color)
    out.putalpha(mask)
    return out.rotate(rng.uniform(0, 360), Image.Resampling.BICUBIC)


def splatter(image, options):
    """Return image with splats behind (and optionally in front of) the opaque text."""
    rng = np.random.default_rng(options.get('seed', 0))
    colors = options.get('colors') or DEFAULT_COLORS
    lo, hi = options.get('size', [60, 180])
    margin = math.ceil(hi * 1.6)
    canvas = Image.new('RGBA', (image.width + 2 * margin, image.height + 2 * margin))
    x0, y0, x1, y1 = image.getchannel('A').point(lambda v: 255 if v > 128 else 0).getbbox() or (0, 0, *image.size)
    w, h = x1 - x0, y1 - y0

    def scatter(count, size_range, spread):
        for _ in range(count):
            sp = blot(rng, max(4, round(rng.uniform(*size_range))), colors[rng.integers(len(colors))])
            x = margin + x0 + rng.uniform(-spread, 1 + spread) * w - sp.width / 2
            y = margin + y0 + rng.uniform(-spread, 1 + spread) * h - sp.height / 2
            canvas.alpha_composite(sp, (round(x), round(y)))

    scatter(options.get('count', 12), (lo, hi), 0.15)
    canvas.alpha_composite(image, (margin, margin))
    scatter(options.get('front', 0), (lo / 4, lo / 2), 0)
    return canvas
