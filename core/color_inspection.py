"""Inspect painted PDF color spaces in text, graphics, Forms and images."""
import re

import pikepdf

from core.image_inspection import inspect_images


def painted_color_spaces(doc):
    pages = [set() for _ in doc]
    for image in inspect_images(doc):
        pages[image['page']].add(image['colorspace'])
    with pikepdf.Pdf.new() as parser:
        def resource(container, key):
            visited = set()
            while container and container not in visited:
                visited.add(container)
                kind, value = doc.xref_get_key(container, 'Resources/' + key)
                if kind != 'null': return kind, value
                parent = doc.xref_get_key(container, 'Parent')
                container = int(parent[1].split()[0]) if parent[0] == 'xref' else 0
            return 'null', 'null'

        def space(name, container):
            names = {'/DeviceRGB': 'RGB', '/DeviceCMYK': 'CMYK', '/DeviceGray': '灰階'}
            name = str(name)
            if name in names: return names[name]
            kind, value = resource(container, 'ColorSpace/' + name.lstrip('/'))
            if kind == 'name': return names.get(value, value.lstrip('/'))
            if kind == 'xref': value = doc.xref_object(int(value.split()[0]))
            if '/ICCBased' in value:
                refs = re.findall(r'(\d+)\s+0\s+R', value)
                if refs:
                    count = doc.xref_get_key(int(refs[0]), 'N')[1]
                    return {'1':'灰階', '3':'RGB', '4':'CMYK'}.get(count, 'ICCBased')
            if '/CalRGB' in value: return 'RGB'
            if '/CalGray' in value: return '灰階'
            if '/Separation' in value or '/DeviceN' in value: return '專色'
            if '/Lab' in value: return 'Lab'
            return name.lstrip('/')

        def scan(payload, container, colors, initial=('灰階', '灰階', 0), ancestors=()):
            if len(ancestors) > 50: raise ValueError('色彩檢查遇到過深的 Form 結構。')
            fill, stroke, text_mode = initial
            stack = []
            stream = pikepdf.Stream(parser, payload)
            for instruction in pikepdf.parse_content_stream(stream):
                op = str(instruction.operator)
                args = instruction.operands
                if op == 'q': stack.append((fill, stroke, text_mode))
                elif op == 'Q' and stack: fill, stroke, text_mode = stack.pop()
                elif op in ('rg', 'k', 'g'): fill = {'rg':'RGB','k':'CMYK','g':'灰階'}[op]
                elif op in ('RG', 'K', 'G'): stroke = {'RG':'RGB','K':'CMYK','G':'灰階'}[op]
                elif op == 'cs': fill = space(args[0], container)
                elif op == 'CS': stroke = space(args[0], container)
                elif op == 'Tr': text_mode = int(args[0])
                elif op in ('f', 'F', 'f*'): colors.add(fill)
                elif op in ('S', 's'): colors.add(stroke)
                elif op in ('B', 'B*', 'b', 'b*'): colors.update((fill, stroke))
                elif op in ('Tj', 'TJ', "'", '"'):
                    if text_mode in (0, 2, 4, 6): colors.add(fill)
                    if text_mode in (1, 2, 5, 6): colors.add(stroke)
                elif op == 'Do':
                    kind, value = resource(container, 'XObject/' + str(args[0]).lstrip('/'))
                    if kind == 'xref':
                        xref = int(value.split()[0])
                        if doc.xref_get_key(xref, 'Subtype')[1] == '/Form':
                            if xref in ancestors: raise ValueError('色彩檢查遇到循環 Form 結構。')
                            owner = xref if doc.xref_get_key(xref, 'Resources')[0] != 'null' else container
                            scan(doc.xref_stream(xref), owner, colors, (fill, stroke, text_mode), ancestors+(xref,))

        for page in doc:
            scan(b'\n'.join(doc.xref_stream(xref) for xref in page.get_contents()), page.xref, pages[page.number])
    return pages
