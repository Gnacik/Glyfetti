"""Deterministic, non-rotating atlas packing with transparent gutters."""
import math


def power_of_two(value):
    return 1 << math.ceil(math.log2(max(value, 1)))


def shelf_pack(sizes, width, pad, max_height=8192):
    x = y = row_h = 0
    positions = []
    for w, h in sizes:
        if w + 2 * pad > width:
            raise ValueError(f'atlas_width: glyph width {w} needs at least {w + 2 * pad}px; increase atlas_width')
        if x + w + pad > width:
            x, y, row_h = 0, y + row_h + pad, 0
        positions.append((x + pad, y + pad))
        x += w + pad
        row_h = max(row_h, h)
    height = power_of_two(y + row_h + 2 * pad)
    if height > max_height:
        raise ValueError(f'max_atlas_size: atlas height {height}px exceeds {max_height}px; increase atlas_width, reduce size or use fewer characters')
    return positions, height


def _maxrects(sizes, width, height, pad):
    free = [(pad, pad, width - pad, height - pad)]
    positions = [None] * len(sizes)
    order = sorted(range(len(sizes)), key=lambda i: (-max(sizes[i]), -math.prod(sizes[i]), i))
    for index in order:
        w, h = (dimension + pad for dimension in sizes[index])
        options = [(min(fw - w, fh - h), max(fw - w, fh - h), y, x)
                   for x, y, fw, fh in free if w <= fw and h <= fh]
        if not options:
            return None
        _, _, y, x = min(options)
        positions[index] = (x, y)
        split = []
        for fx, fy, fw, fh in free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                split.append((fx, fy, fw, fh))
                continue
            if x > fx:
                split.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                split.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                split.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                split.append((fx, y + h, fw, fy + fh - y - h))
        # MaxRects free rectangles can overlap, but contained duplicates are redundant.
        unique = sorted(set(split))
        free = [r for r in unique if not any(
            r != other and r[0] >= other[0] and r[1] >= other[1]
            and r[0] + r[2] <= other[0] + other[2]
            and r[1] + r[3] <= other[1] + other[3]
            for other in unique)]
    return positions


def pack_atlas(sizes, width, pad=2, max_height=8192, method='maxrects'):
    """Choose the smallest successful power-of-two height, never worse than shelf."""
    if method == 'shelf':
        positions, height = shelf_pack(sizes, width, pad, max_height)
        return positions, height, 'shelf'
    if method != 'maxrects':
        raise ValueError(f'atlas_packing: unsupported method {method}')
    for w, h in sizes:
        if w + 2 * pad > width:
            raise ValueError(f'atlas_width: glyph width {w} needs at least {w + 2 * pad}px; increase atlas_width')
        if h + 2 * pad > max_height:
            raise ValueError(f'max_atlas_size: glyph height {h}px exceeds available atlas height')
    try:
        shelf = shelf_pack(sizes, width, pad, max_height)
    except ValueError:
        shelf = None
    minimum = max((h + 2 * pad for w, h in sizes), default=2 * pad)
    area = sum((w + pad) * (h + pad) for w, h in sizes)
    height = power_of_two(max(minimum, math.ceil(area / max(width - pad, 1)) + pad))
    limit = min(max_height, shelf[1] if shelf else max_height)
    while height <= limit:
        positions = _maxrects(sizes, width, height, pad)
        if positions is not None:
            return positions, height, 'maxrects'
        height *= 2
    if shelf:
        return shelf[0], shelf[1], 'shelf'
    raise ValueError('max_atlas_size: glyphs do not fit; increase atlas_width, reduce size or use fewer characters')
