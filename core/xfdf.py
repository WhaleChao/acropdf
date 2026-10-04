"""Standard XFDF annotation exchange without engine-specific empty-file fallbacks."""
from pathlib import Path
import math
import re
import xml.etree.ElementTree as ET
import fitz
from core.file_io import atomic_output

NS = 'http://ns.adobe.com/xfdf/'
ET.register_namespace('', NS)
TYPES = {0:'text', 2:'freetext', 3:'line', 4:'square', 5:'circle', 6:'polygon', 7:'polyline',
         8:'highlight', 9:'underline', 10:'squiggly', 11:'strikeout', 12:'stamp', 15:'ink', 12+2:'caret', 12+13:'redact'}
# MuPDF's redaction subtype is 12, stamp is 13, caret is 14.
TYPES[fitz.PDF_ANNOT_REDACT] = 'redact'; TYPES[fitz.PDF_ANNOT_STAMP] = 'stamp'
TYPES[fitz.PDF_ANNOT_CARET] = 'caret'
SUPPORTED = {'text','freetext','line','square','circle','polygon','polyline','highlight','underline','squiggly','strikeout','stamp','ink','redact','caret'}


def _numbers(value, count=None):
    values=[float(v) for v in re.split(r'[,;\s]+', value.strip()) if v]
    if (count is not None and len(values)!=count) or not all(math.isfinite(v) for v in values):
        raise ValueError('XFDF 座標無效。')
    return values


def _points(vertices, matrix):
    return [fitz.Point(v)*matrix for v in vertices]


def _coords(points):
    return ','.join(f'{n:.6f}' for point in points for n in point)


def export_annotations(document, destination):
    root=ET.Element(f'{{{NS}}}xfdf', {'{http://www.w3.org/XML/1998/namespace}space':'preserve'})
    annots=ET.SubElement(root,f'{{{NS}}}annots')
    for page in document.fitz_doc:
        matrix=~page.transformation_matrix
        for annot in page.annots() or ():
            subtype=TYPES.get(annot.type[0])
            if subtype not in SUPPORTED: raise ValueError(f'XFDF 尚不能交換 {annot.type[1]}，未產生不完整輸出。')
            rect=annot.rect*matrix
            attrs={'page':str(page.number),'rect':','.join(str(n) for n in rect),'opacity':str(annot.opacity if annot.opacity>=0 else 1),'flags':str(annot.flags)}
            info=annot.info
            if subtype=='stamp':
                stamp_name=document.fitz_doc.xref_get_key(annot.xref,'Name')[1].lstrip('/')
                attrs['name']=stamp_name
            for key in ('title','subject','name'):
                if info.get(key): attrs[key]=info[key]
            colors=annot.colors
            if colors.get('stroke'):
                color=colors['stroke']
                if len(color)==1: color=color*3
                if len(color)==4:
                    c,m,y,k=color;color=(1-min(1,c+k),1-min(1,m+k),1-min(1,y+k))
                attrs['color']='#'+''.join(f'{round(max(0,min(1,c))*255):02X}' for c in color[:3])
            attrs['width']=str(annot.border.get('width',1))
            element=ET.SubElement(annots,f'{{{NS}}}{subtype}',attrs)
            ET.SubElement(element,f'{{{NS}}}contents').text=info.get('content','')
            vertices=annot.vertices
            if subtype in ('highlight','underline','squiggly','strikeout'):
                element.set('coords',_coords(_points(vertices,matrix)))
            elif subtype=='line':
                element.set('start',_coords(_points(vertices[:1],matrix)));element.set('end',_coords(_points(vertices[1:2],matrix)))
            elif subtype in ('polygon','polyline'):
                ET.SubElement(element,f'{{{NS}}}vertices').text=_coords(_points(vertices,matrix))
            elif subtype=='ink':
                ink=ET.SubElement(element,f'{{{NS}}}inklist')
                for stroke in vertices: ET.SubElement(ink,f'{{{NS}}}gesture').text=_coords(_points(stroke,matrix))
    data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    with atomic_output(destination,source=document.source_path) as stage: stage.write_bytes(data)
    return str(destination)


def import_annotations(document, source):
    path=Path(source)
    if path.stat().st_size>10*1024*1024: raise ValueError('XFDF 超過 10 MiB。')
    data=path.read_bytes()
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise ValueError('XFDF 不接受外部實體。')
    root=ET.fromstring(data)
    if root.tag!=f'{{{NS}}}xfdf': raise ValueError('這不是有效的 XFDF 文件。')
    entries=list(root.findall(f'{{{NS}}}annots/*'))
    # Validate everything before starting a transaction, then roll back on any creation error.
    prepared=[]
    for element in entries:
        kind=element.tag.rsplit('}',1)[-1]
        if kind not in SUPPORTED: raise ValueError(f'不支援的 XFDF 標注：{kind}')
        index=int(element.attrib['page'])
        if not 0<=index<document.page_count: raise ValueError('XFDF 頁碼超出文件範圍。')
        rect=fitz.Rect(_numbers(element.attrib['rect'],4))
        if rect.is_empty or rect.is_infinite: raise ValueError('XFDF 標注範圍無效。')
        prepared.append((element,kind,index,rect))
    with document.edit_transaction('匯入 XFDF 標注'):
        for element,kind,index,pdfrect in prepared:
            page=document.fitz_doc[index];matrix=page.transformation_matrix;rect=pdfrect*matrix
            content=element.findtext(f'{{{NS}}}contents',default='')
            def coordinates(value):
                nums=_numbers(value)
                if len(nums)%2: raise ValueError('XFDF 座標配對無效。')
                return [fitz.Point(nums[i:i+2])*matrix for i in range(0,len(nums),2)]
            if kind in ('highlight','underline','strikeout','squiggly'):
                points=coordinates(element.attrib['coords'])
                if not points or len(points)%4: raise ValueError('XFDF 四邊形無效。')
                quads=[fitz.Quad(points[i:i+4]) for i in range(0,len(points),4)]
                annot=getattr(page,f'add_{kind}_annot')(quads)
            elif kind=='text': annot=page.add_text_annot(rect.tl,content)
            elif kind=='freetext': annot=page.add_freetext_annot(rect,content,fontname='china-t' if any(ord(c)>255 for c in content) else 'helv')
            elif kind=='square': annot=page.add_rect_annot(rect)
            elif kind=='circle': annot=page.add_circle_annot(rect)
            elif kind=='redact': annot=page.add_redact_annot(rect,text=content)
            elif kind=='caret': annot=page.add_caret_annot(rect.tl)
            elif kind=='stamp':
                name=element.get('name','Approved');number=getattr(fitz,'STAMP_'+name,None)
                if number is None: raise ValueError('XFDF 自訂圖章需要外觀資源，未替換成其他圖章。')
                annot=page.add_stamp_annot(rect,stamp=number)
            elif kind=='line': annot=page.add_line_annot(coordinates(element.attrib['start'])[0],coordinates(element.attrib['end'])[0])
            elif kind in ('polygon','polyline'): annot=getattr(page,f'add_{kind}_annot')(coordinates(element.findtext(f'{{{NS}}}vertices',default='')))
            elif kind=='ink': annot=page.add_ink_annot([coordinates(g.text or '') for g in element.findall(f'{{{NS}}}inklist/{{{NS}}}gesture')])
            annot.set_info(content=content,title=element.get('title',''),subject=element.get('subject',''))
            color=element.get('color','')
            if re.fullmatch(r'#[0-9A-Fa-f]{6}',color): annot.set_colors(stroke=tuple(int(color[i:i+2],16)/255 for i in (1,3,5)))
            opacity=float(element.get('opacity','1'))
            if not 0<=opacity<=1: raise ValueError('XFDF 透明度無效。')
            annot.set_opacity(opacity);annot.set_flags(int(element.get('flags','4')))
            if kind in ('square','circle','line','polygon','polyline','ink'): annot.set_border(width=float(element.get('width','1')))
            annot.update()
    return len(prepared)
