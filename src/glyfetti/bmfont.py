import struct
import xml.etree.ElementTree as ET

FORMATS = ('text', 'xml', 'binary')
CHAR_FIELDS = ('id', 'x', 'y', 'width', 'height', 'xoffset', 'yoffset', 'xadvance')


def bmfont_bytes(fmt, face, size, line_height, base, scale_w, scale_h, pages, chars, kernings):
    if isinstance(pages, str):
        pages = [pages]
    info = {'face': face, 'size': size, 'bold': 0, 'italic': 0, 'charset': '', 'unicode': 1, 'stretchH': 100,
            'smooth': 1, 'aa': 1, 'padding': '0,0,0,0', 'spacing': '2,2'}
    common = {'lineHeight': line_height, 'base': base, 'scaleW': scale_w, 'scaleH': scale_h, 'pages': len(pages), 'packed': 0}
    chars = [dict({k: c[k] for k in CHAR_FIELDS}, page=c.get('page', 0), chnl=15) for c in chars]
    if fmt == 'text':
        def line(tag, values):
            return ' '.join([tag] + [f'{k}="{v}"' if k in ('face', 'charset', 'file') else f'{k}={v}' for k, v in values.items()])
        lines = [line('info', info), line('common', common)] + [line('page', {'id': i, 'file': f}) for i, f in enumerate(pages)]
        lines.append(f'chars count={len(chars)}')
        lines += [line('char', c) for c in chars]
        lines.append(f'kernings count={len(kernings)}')
        lines += [line('kerning', k) for k in kernings]
        return ('\n'.join(lines) + '\n').encode('utf-8')
    if fmt == 'xml':
        root = ET.Element('font')
        ET.SubElement(root, 'info', {k: str(v) for k, v in info.items()})
        ET.SubElement(root, 'common', {k: str(v) for k, v in common.items()})
        group = ET.SubElement(root, 'pages')
        for i, f in enumerate(pages):
            ET.SubElement(group, 'page', {'id': str(i), 'file': f})
        group = ET.SubElement(root, 'chars', {'count': str(len(chars))})
        for c in chars:
            ET.SubElement(group, 'char', {k: str(v) for k, v in c.items()})
        group = ET.SubElement(root, 'kernings', {'count': str(len(kernings))})
        for k in kernings:
            ET.SubElement(group, 'kerning', {key: str(value) for key, value in k.items()})
        ET.indent(root)
        return b'<?xml version="1.0"?>\n' + ET.tostring(root, encoding='utf-8', xml_declaration=False) + b'\n'

    def block(kind, data):
        return struct.pack('<BI', kind, len(data)) + data

    out = b'BMF\x03'
    out += block(1, struct.pack('<hBBHBBBBBBBB', size, 0xC0, 0, 100, 1, 0, 0, 0, 0, 2, 2, 0) + face.encode('utf-8') + b'\0')
    out += block(2, struct.pack('<HHHHHBBBBB', line_height, base, scale_w, scale_h, len(pages), 0, 0, 0, 0, 0))
    out += block(3, b''.join(f.encode('utf-8') + b'\0' for f in pages))
    out += block(4, b''.join(struct.pack('<IHHHHhhhBB', *(c[k] for k in CHAR_FIELDS + ('page', 'chnl'))) for c in chars))
    if kernings:
        out += block(5, b''.join(struct.pack('<IIh', k['first'], k['second'], k['amount']) for k in kernings))
    return out
