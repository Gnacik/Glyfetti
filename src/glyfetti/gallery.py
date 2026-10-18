"""Render every preset in a folder and compose a gallery sheet (PNG)."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .engine import build, FONTS_DIR

TW, TH, COLS, GAP = 900, 330, 2, 24


def _font(size, weight=800):
    f = ImageFont.truetype(str(FONTS_DIR / 'Baloo2.ttf'), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def make_gallery(preset_dir, out_png, title='Glyfetti presets',
                 subtitle='one JSON file per style  •  full character sets  •  BMFont / JSON / Unity TMP export'):
    preset_dir = Path(preset_dir)
    work = preset_dir / 'out'
    styles = sorted(preset_dir.glob('*.json'), key=lambda p: json.loads(p.read_text('utf-8')).get('order', 999))
    rows = (len(styles) + COLS - 1) // COLS
    W = COLS * TW + (COLS + 1) * GAP
    H = 150 + rows * (TH + 80 + GAP) + GAP
    sheet = Image.new('RGB', (W, H), '#F6F2EA')
    d = ImageDraw.Draw(sheet)
    d.text((GAP, 22), title, fill='#2B2118', font=_font(58))
    d.text((GAP, 100), subtitle, fill='#6B5D4F', font=_font(26, 600))
    for i, sp in enumerate(styles):
        st = json.loads(sp.read_text('utf-8'))
        build(sp, out_dir=work, preview_only=True)
        x = GAP + (i % COLS) * (TW + GAP)
        y = 150 + (i // COLS) * (TH + 80 + GAP)
        tile = Image.new('RGB', (TW, TH), st.get('preview_bg', '#ffffff'))
        pv = Image.open(work / f"{st['name']}_preview.png").convert('RGBA')
        s = min((TW - 60) / pv.width, (TH - 30) / pv.height, 1.0)
        pv = pv.resize((round(pv.width * s), round(pv.height * s)), Image.LANCZOS)
        tile.paste(pv, ((TW - pv.width) // 2, (TH - pv.height) // 2), pv)
        sheet.paste(tile, (x, y))
        d.rounded_rectangle((x, y, x + TW, y + TH), 14, outline='#D8CFC2', width=2)
        label = f"{i + 1}. {st['name']}"
        d.text((x, y + TH + 6), label, fill='#2B2118', font=_font(30))
        d.text((x + d.textlength(label, font=_font(30)) + 14, y + TH + 13),
               f"· {st.get('font_label', Path(st['font']).stem)}", fill='#8A7A68', font=_font(22, 600))
        d.text((x, y + TH + 44), st.get('description', ''), fill='#5E5042', font=_font(21, 500))
    sheet.save(out_png)
    return out_png
