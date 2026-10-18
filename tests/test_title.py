import io
import json

import numpy as np
from PIL import Image
import pytest

from glyfetti.cli import main
from glyfetti.engine import build, FONTS_DIR
from glyfetti.server import render_style
from glyfetti.title import build_title, title_image


@pytest.fixture
def style():
    return {'name': 'title', 'font': str(FONTS_DIR / 'TitanOne-Regular.ttf'),
            'size': 40, 'supersample': 1, 'chars': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'fill': {'stops': [[0, '#ffffff']]}, 'outline': {'color': '#ff0000', 'width': 3},
            'preview': ['AV To', 'Glyfetti'], 'preview_bg': '#123456',
            'title': {'align': 'center', 'padding': 8}}


def write_style(style, tmp_path):
    path = tmp_path / 'style.json'
    path.write_text(json.dumps(style, ensure_ascii=False), 'utf-8')
    return path


def test_png_is_transparent_with_exact_padding_and_separate_background_preview(style, tmp_path):
    source = write_style(style, tmp_path)
    result = build_title(source)
    with Image.open(result['out']) as image, Image.open(result['preview']) as preview:
        assert image.mode == 'RGBA'
        assert image.size == tuple(result['size']) == preview.size
        assert image.getpixel((0, 0)) == (0, 0, 0, 0)
        assert image.getbbox() == (8, 8, image.width - 8, image.height - 8)
        assert preview.getpixel((0, 0)) == (0x12, 0x34, 0x56, 255)
    assert not list((tmp_path / 'out').glob('*.fnt'))


@pytest.mark.parametrize('alignment,fraction', [('left', 0), ('center', .5), ('right', 1)])
def test_multiline_alignment_uses_visible_letter_bounds(style, alignment, fraction):
    style.update(preview=['MMMM', 'I'], outline={'color': '#000000', 'width': 0}, line_height=2)
    style['title']['align'] = alignment
    image, report = title_image(style, '.')
    alpha = np.asarray(image)[..., 3]
    nonempty = np.where(alpha.max(axis=1) > 0)[0]
    split = np.where(np.diff(nonempty) > 1)[0][0] + 1
    top_rows, bottom_rows = nonempty[:split], nonempty[split:]
    top_x = np.where(alpha[top_rows].max(axis=0) > 0)[0]
    bottom_x = np.where(alpha[bottom_rows].max(axis=0) > 0)[0]
    # Pixel columns occupied by M may have gaps, so use actual extents.
    expected = top_x.min() + round(((top_x.max() - top_x.min()) - (bottom_x.max() - bottom_x.min())) * fraction)
    assert abs(bottom_x.min() - expected) <= 1
    assert report['lines'] == 2


def test_shared_outline_removes_internal_letter_seams(style, tmp_path):
    style.update(preview=['II'], chars='I', tracking=-10, preview_bg='transparent')
    source = write_style(style, tmp_path)
    build(source, tmp_path / 'atlas')
    image, _ = title_image(style, tmp_path)
    def red_pixels(image):
        pixels = np.asarray(image)
        return np.count_nonzero((pixels[..., 0] > 240) & (pixels[..., 1] < 10) & (pixels[..., 3] > 240))
    with Image.open(tmp_path / 'atlas/title_preview.png') as separate:
        assert red_pixels(image) < red_pixels(separate)


def test_title_kerning_and_condense_affect_real_image_width(style):
    style['preview'] = ['AV']
    kerned, _ = title_image(style, '.')
    style['kerning'] = False
    plain, _ = title_image(style, '.')
    assert kerned.width < plain.width
    style['condense'] = .6
    condensed, _ = title_image(style, '.')
    assert condensed.width < plain.width


def test_title_reports_missing_characters_and_composes_polish_letters(style, tmp_path):
    style.update(font=str(FONTS_DIR / 'Chewy-Regular.ttf'), preview=['Zażółć ąęńśź 😀'])
    image, report = title_image(style, tmp_path)
    assert image.getbbox()
    assert report['skipped'] == '😀'


@pytest.mark.parametrize('text', ['', '   ', '😀'])
def test_empty_or_unsupported_title_fails_without_output(style, tmp_path, text):
    source = write_style(style, tmp_path)
    with pytest.raises(ValueError, match='no supported visible characters'):
        build_title(source, text=text)
    assert not (tmp_path / 'out').exists()


def test_large_title_fails_before_allocating_the_whole_effect_canvas(style, tmp_path):
    style.update(preview=['M' * 1000], size=100, supersample=3)
    source = write_style(style, tmp_path)
    with pytest.raises(ValueError, match='image is too large'):
        build_title(source)
    assert not (tmp_path / 'out').exists()


def test_cli_title_text_override_line_breaks_and_custom_path(style, tmp_path, capsys):
    source = write_style(style, tmp_path)
    output = tmp_path / 'nested' / 'victory.png'
    assert main(['title', str(source), '--text', 'Win!\nZażółć', '--align', 'right', '-o', str(output)]) == 0
    assert output.is_file()
    assert output.with_name('victory_preview.png').is_file()
    assert 'title ' in capsys.readouterr().out


@pytest.mark.parametrize('options', [{'align': 'diagonal'}, {'padding': -1}, {'padding': 201}])
def test_invalid_title_options_are_rejected(style, options):
    style['title'] = options
    with pytest.raises(ValueError, match='title'):
        title_image(style, '.')


def test_png_extension_is_required(style, tmp_path):
    with pytest.raises(ValueError, match='.png'):
        build_title(write_style(style, tmp_path), tmp_path / 'bad.jpg')


def test_title_server_exports_png_instead_of_atlas_zip(style):
    preview = render_style(style, preview=True, mode='title')
    assert preview['mode'] == 'title'
    assert preview['image'].startswith('data:image/png;base64,iVBOR')
    exported = render_style(style, mode='title')
    assert exported.startswith(b'\x89PNG\r\n\x1a\n')
    with Image.open(io.BytesIO(exported)) as image:
        assert image.mode == 'RGBA'
        assert image.getpixel((0, 0))[3] == 0


def test_every_preset_supports_title_draft(tmp_path):
    from glyfetti.server import catalog
    for style in catalog()['presets']:
        style['supersample'] = 1
        image, report = title_image(style, tmp_path)
        assert image.getbbox(), style['name']
        assert not report['skipped'], style['name']
