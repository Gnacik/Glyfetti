"""Deterministic high-level styling expanded into the renderer's raw format."""
import copy

PALETTES = {
    'gold': (['#FFF1BC', '#FCE288', '#F8C95A'], '#EFA032', '#C46A14', '#562506'),
    'cream': (['#FFFDF5', '#FBF0D6', '#F1DDB0'], '#C9A36B', '#8E6838', '#3E1E0A'),
    'candy': (['#FFE6F1', '#FF9CC7', '#FF5E9E'], '#E2457F', '#9E1C50', '#5A0F2E'),
    'mint': (['#FFFFFF', '#E6FFD9'], '#3F8F2E', '#27611B', '#1F4D17'),
    'ice': (['#FFFFFF', '#C8F0FF', '#62C2F2'], '#2E8FD2', '#174F88', '#0E2F55'),
    'fire': (['#FFF8B5', '#FFC93C', '#FF5E14'], '#D23A10', '#7E1404', '#3A0A02'),
    'magic': (['#FAF0FF', '#CFA6FF', '#8C55F0'], '#6234C2', '#38197A', '#1E0D40'),
    'wood': (['#D39657', '#8B5426'], '#5A3215', '#3B1F0B', '#3B1F0B'),
    'silver': (['#FFFFFF', '#D5DCE3', '#8C96A1', '#C9D1D9', '#EEF2F5'], '#5C6671', '#2F363E', '#1B2026'),
}
FONTS = {'Titan One': 'TitanOne-Regular.ttf', 'Grandstander': 'Grandstander.ttf',
         'Baloo 2': 'Baloo2.ttf', 'Dosis': 'Dosis.ttf', 'Chewy': 'Chewy-Regular.ttf',
         'Sniglet': 'Sniglet-ExtraBold.ttf'}
DEFAULT_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZĄĆĘŁŃÓŚŹŻabcdefghijklmnopqrstuvwxyząćęłńóśźż0123456789!?.,:;%+-()[]/@#€ '


def mix(color, target, amount):
    first = [int(color[index:index + 2], 16) for index in (1, 3, 5)]
    second = [int(target[index:index + 2], 16) for index in (1, 3, 5)]
    return '#' + ''.join(f'{round(a + (b - a) * amount):02X}' for a, b in zip(first, second))


def merge(base, override):
    """Objects merge recursively; arrays, nulls and scalars replace in full."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else copy.deepcopy(value)
    return result


def _rounded(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def expand_simple(style):
    if 'simple' not in style:
        return copy.deepcopy(style)
    from .validation import DATA_DIR
    options = style['simple']
    base = options.get('base_color')
    if base:
        fill = [mix(base, '#FFFFFF', .7), mix(base, '#FFFFFF', .3), base.upper()]
        side_top, side_bottom, dark = mix(base, '#000000', .2), mix(base, '#000000', .5), mix(base, '#000000', .8)
    else:
        fill, side_top, side_bottom, dark = PALETTES[options.get('palette', 'gold')]
    size = style.get('size', 90)
    scale = size / 100
    outline = options.get('outline', 'dark')
    outline_color = {'dark': dark, 'light': mix(fill[0], '#FFFFFF', .85), 'none': dark}.get(outline, outline)
    width = options.get('outline_width', 'medium')
    width = {'thin': 2.5, 'medium': 4, 'thick': 6}[width] * scale if isinstance(width, str) else width
    depth, shine, playful = options.get('depth_3d', .5), options.get('shine', .4), options.get('playful', 0)
    shadow_kind = options.get('shadow', 'soft')
    shadow = {'enabled': shadow_kind != 'none', 'color': dark, 'opacity': .45, 'dx': scale, 'dy': 7 * scale, 'blur': 5 * scale}
    if shadow_kind == 'hard':
        shadow.update(dx=5 * scale, dy=5 * scale, blur=0, opacity=.8)
    elif shadow_kind == 'long':
        shadow.update(dx=10 * scale, dy=14 * scale, blur=3 * scale, opacity=.55)
    if options.get('glow'):
        shadow.update(enabled=True, color=options['glow'], dx=0, dy=0, blur=12 * scale, opacity=.8)
    defaults = {
        'font': 'Titan One', 'size': 90, **({} if 'charset' in style else {'chars': DEFAULT_CHARS}), 'atlas_width': 2048,
        'preview': ['Level Complete!', 'Score: 2 560'], 'preview_bg': '#F5F1E8',
        'fill': {'stops': [[index / (len(fill) - 1), color] for index, color in enumerate(fill)]},
        'outline': {'color': outline_color, 'width': 0 if outline == 'none' else width},
        'side': {'enabled': depth > 0, 'depth': min(40, depth * 10 * scale), 'dx': depth * 2 * scale,
                 'color_top': side_top, 'color_bottom': side_bottom},
        'bevel': {'enabled': shine > 0, 'size': 4 * scale, 'light_angle': 110,
                  'highlight_color': mix(fill[0], '#FFFFFF', .85), 'highlight_strength': shine * .8,
                  'shadow_color': side_top, 'shadow_strength': shine * .5},
        'gloss': {'enabled': shine > 0, 'color': '#FFFFFF', 'opacity': shine * .6, 'inset': 3 * scale, 'height': .4, 'blur': 3 * scale},
        'shadow': shadow, 'condense': options.get('width', 1), 'embolden': options.get('weight', 0),
        'tracking': options.get('spacing', 0),
        'jitter': {'rotate': playful * 6, 'y': playful * 4 * scale, 'seed': 11} if playful else None,
    }
    raw = merge(_rounded(defaults), {key: value for key, value in style.items() if key != 'simple'})
    if raw['font'] in FONTS:
        raw['font'] = str((DATA_DIR / 'fonts' / FONTS[raw['font']]).resolve())
    return raw
