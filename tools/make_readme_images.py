"""Regenerate the README images in docs/images (hero, before/after, layer breakdown, gallery)."""
import copy, json, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from glyfetti.engine import build
from glyfetti.gallery import make_gallery

ROOT = Path(__file__).resolve().parents[1]
P, OUT = ROOT / 'presets', ROOT / 'docs' / 'images'
T = Path(tempfile.mkdtemp())


def st(name):
    return json.loads((P / f'{name}.json').read_text('utf-8'))


def render(s, nm):
    s = copy.deepcopy(s); s['name'] = nm; s['preview_bg'] = 'transparent'
    s['font'] = str((P / s['font']).resolve())
    f = T / f'{nm}.json'; f.write_text(json.dumps(s, ensure_ascii=False), 'utf-8')
    build(f, out_dir=T, preview_only=True)
    im = Image.open(T / f'{nm}_preview.png').convert('RGBA')
    return im.crop(im.getbbox())


def lab(sz, w=800):
    F = ImageFont.truetype(str(ROOT / 'fonts' / 'Baloo2.ttf'), sz); F.set_variation_by_axes([w]); return F


def hero():
    g = st('honey_gold'); g.update(size=190, preview=['Glyfetti']); g['jitter'] = {"rotate": 3, "y": 3, "seed": 2}
    c = st('candy_pink'); c.update(size=64, preview=['Make your letters pop!'])
    logo, tag = render(g, 'hero_logo'), render(c, 'hero_tag')
    W, H = 1600, 520
    im = Image.new('RGB', (W, H)); d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H; d.line([(0, y), (W, y)], fill=(int(255 - 30 * t), int(236 - 40 * t), int(205 - 60 * t)))
    im = im.convert('RGBA')
    im.alpha_composite(logo, ((W - logo.width) // 2, 40))
    im.alpha_composite(tag, ((W - tag.width) // 2, 40 + logo.height + 5))
    d = ImageDraw.Draw(im); s = 'Styled game text & bitmap font atlases  •  Unity TextMeshPro  •  BMFont  •  AI-ready'
    d.text(((W - d.textlength(s, font=lab(30, 600))) // 2, H - 70), s, fill='#6B4A2B', font=lab(30, 600))
    im.convert('RGB').save(OUT / 'hero.png')


def before_after():
    F = ImageFont.truetype(str(ROOT / 'fonts' / 'TitanOne-Regular.ttf'), 90)
    tmp = Image.new('RGBA', (1000, 180), (0, 0, 0, 0)); ImageDraw.Draw(tmp).text((10, 10), 'Level Complete!', font=F, fill='#222222')
    plain = tmp.crop(tmp.getbbox())
    h = st('honey_gold'); h.update(preview=['Level Complete!']); after = render(h, 'ba_after')
    W, H = 1600, 300
    im = Image.new('RGBA', (W, H), '#FFFFFF'); im.paste(Image.new('RGBA', (W // 2, H), '#8B5A2B'), (W // 2, 0))
    for src, x0 in ((plain, 0), (after, W // 2)):
        s = min(1, (W // 2 - 80) / src.width); r = src.resize((int(src.width * s), int(src.height * s)), Image.LANCZOS)
        im.alpha_composite(r, (x0 + (W // 2 - r.width) // 2, (H - r.height) // 2 + 15))
    d = ImageDraw.Draw(im)
    d.text((24, 14), 'Plain font (Titan One)', fill='#555555', font=lab(28))
    d.text((W // 2 + 24, 14), 'glyfetti build honey_gold.json', fill='#FFE9B8', font=lab(28))
    im.convert('RGB').save(OUT / 'before_after.png')


def layers():
    base = st('honey_gold'); base.update(size=120, preview=['Aa'], jitter=None)
    steps = [('fill', []), ('+ outline', ['outline']), ('+ 3D side', ['outline', 'side']),
             ('+ bevel', ['outline', 'side', 'bevel']), ('+ gloss', ['outline', 'side', 'bevel', 'gloss']),
             ('+ shadow', ['outline', 'side', 'bevel', 'gloss', 'shadow'])]
    tiles = []
    for i, (nm, on) in enumerate(steps):
        s = copy.deepcopy(base)
        for L in ['side', 'bevel', 'gloss', 'shadow']:
            if L not in on:
                s[L] = {"enabled": False}
        if 'outline' not in on:
            s['outline'] = {"color": "#000000", "width": 0}
        tiles.append((nm, render(s, f'layer{i}')))
    TW, H = 260, 300; W = TW * len(tiles) + 40
    im = Image.new('RGBA', (W, H), '#8B5A2B'); d = ImageDraw.Draw(im)
    for i, (nm, t) in enumerate(tiles):
        x = 20 + i * TW
        im.alpha_composite(t, (x + (TW - t.width) // 2, 30 + (200 - t.height) // 2))
        d.text((x + (TW - d.textlength(nm, font=lab(30))) // 2, H - 60), nm, fill='#FFF1BC', font=lab(30))
    im.convert('RGB').save(OUT / 'layers.png')


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    hero(); before_after(); layers()
    make_gallery(P, OUT / 'gallery.png')
    print('images ->', OUT)
