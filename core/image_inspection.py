"""Inspect painted image placements, including inline and rotated images."""
import math


def inspect_images(doc, interrupted=None, progress=None):
    results = []
    for page_number, page in enumerate(doc):
        if interrupted and interrupted():
            raise InterruptedError("影像檢查已取消。")
        for image in page.get_image_info(xrefs=True):
            if interrupted and interrupted():
                raise InterruptedError("影像檢查已取消。")
            a, b, c, d, _, _ = image['transform']
            # The transform maps the unit image square to the page. Bounding
            # boxes exchange axes on rotation and overestimate sizes on shear.
            width_points, height_points = math.hypot(a, b), math.hypot(c, d)
            dpi_x = image['width'] * 72 / width_points if width_points else 0
            dpi_y = image['height'] * 72 / height_points if height_points else 0
            results.append({
                'page': page_number, 'xref': image.get('xref', 0),
                'width': image['width'], 'height': image['height'],
                'dpi_x': dpi_x, 'dpi_y': dpi_y, 'dpi': min(dpi_x, dpi_y),
                'colorspace': {1: '灰階', 3: 'RGB', 4: 'CMYK'}.get(image.get('colorspace'), image.get('cs-name') or 'Unknown'),
                'bbox': tuple(image['bbox']),
            })
        if progress:
            progress(round(100 * (page_number + 1) / max(len(doc), 1)))
    return results
