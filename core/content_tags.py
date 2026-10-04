"""Create content-linked tags with MCIDs and ParentTree, preserving page painting.

Reading order follows source painting order and needs a human semantic review.
Existing structure trees are preserved and must be edited, never replaced automatically.
"""
import io
import re
import fitz
import pikepdf


def _ref(xref): return f'{xref} 0 R'

def _new(doc, value):
    xref=doc.get_new_xref();doc.update_object(xref,value);return xref


def tag_document(doc, title, language, image_alts=None, password=''):
    image_alts=image_alts or {}
    if not title.strip(): raise ValueError('請輸入文件標題。')
    if not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*',language): raise ValueError('文件語言無效。')
    catalog=doc.pdf_catalog()
    if doc.xref_get_key(catalog,'StructTreeRoot')[0]!='null': raise ValueError('文件已有結構樹，請保留並編輯既有標記。')
    # A private copy avoids changing the live document's encryption settings.
    with fitz.open('pdf',doc.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP)) as private:
        if private.needs_pass and not private.authenticate(password): raise ValueError('無法認證標記快照。')
        raw=private.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)
    parsed=pikepdf.open(io.BytesIO(raw))
    for page in parsed.pages:
        if page.obj.get('/Annots'): raise ValueError('請先處理表單及標注的閱讀順序，再建立內容標記。')
    root=_new(doc,'<< /Type /StructTreeRoot >>')
    document=_new(doc,f'<< /Type /StructElem /S /Document /P {_ref(root)} >>')
    parents=[];sections=[];seen_forms=set();count=0

    def process(container, stream_xref, page_xref, parent, resources, page_index):
        nonlocal count
        instructions=list(pikepdf.parse_content_stream(container))
        if any(str(op) == 'BDC' and len(args)>1 and isinstance(args[1],pikepdf.Dictionary) and '/MCID' in args[1] for args,op in instructions):
            raise ValueError('來源已含內容標記，請保留既有內容關聯。')
        children=[];mapping=[];out=[];in_text=False
        trace=[span for span in doc[page_index].get_texttrace() if span.get('chars')]
        text_index=0
        for operands,operator in instructions:
            op=str(operator)
            if op in ('BMC','BDC','EMC'):
                out.append((operands,operator));continue
            if op=='BT': in_text=True
            if op=='ET': in_text=False
            tag=None;extra='';bbox=None
            if op in ('Tj','TJ',"'",'"'):
                tag='P'
                if text_index<len(trace): bbox=trace[text_index]['bbox']
                text_index+=1
            elif op=='Do':
                item=resources.get('/XObject',{}).get(operands[0])
                if item is None: raise ValueError('找不到繪圖資源。')
                xref=item.objgen[0]
                if item.get('/Subtype')==pikepdf.Name('/Image'):
                    alt=image_alts.get(xref,'').strip()
                    if not alt: raise ValueError(f'第 {page_index+1} 頁圖片 {xref} 需要替代文字。')
                    tag='Figure';extra='/Alt '+fitz.get_pdf_str(alt)
                elif item.get('/Subtype')==pikepdf.Name('/Form'):
                    if xref in seen_forms: raise ValueError('重複使用的 Form 資源需先展開以建立獨立閱讀順序。')
                    seen_forms.add(xref)
                    section=_new(doc,f'<< /Type /StructElem /S /Sect /P {_ref(parent)} /Pg {_ref(page_xref)} >>')
                    children.append(section)
                    nested=process(item,xref,page_xref,section,item.get('/Resources',resources),page_index)
                    doc.xref_set_key(section,'K','['+' '.join(_ref(n) for n in nested)+']')
            if tag:
                mcid=len(mapping)
                key=(f'/K {mcid}' if stream_xref is None else f'/K << /Type /MCR /Pg {_ref(page_xref)} /Stm {_ref(stream_xref)} /MCID {mcid} >>')
                node=_new(doc,f'<< /Type /StructElem /S /{tag} /P {_ref(parent)} /Pg {_ref(page_xref)} {key} {extra} >>')
                if bbox: doc.xref_set_key(node,'AcroBBox','['+' '.join(str(n) for n in bbox)+']')
                mapping.append(node);children.append(node);count+=1
                out.append(([pikepdf.Name('/'+tag),pikepdf.Dictionary(MCID=mcid)],pikepdf.Operator('BDC')))
                out.append((operands,operator));out.append(([],pikepdf.Operator('EMC')))
            elif op=='Do' and resources.get('/XObject',{}).get(operands[0],{}).get('/Subtype')==pikepdf.Name('/Form'):
                out.append((operands,operator))
            else:
                # Content outside text/image tags is explicitly decorative artifact content.
                out.append(([pikepdf.Name('/Artifact')],pikepdf.Operator('BMC')))
                out.append((operands,operator));out.append(([],pikepdf.Operator('EMC')))
        key=len(parents);parents.append(mapping)
        payload=pikepdf.unparse_content_stream(out)
        if stream_xref is None:
            stream=_new(doc,'<< >>');doc.update_stream(stream,payload)
            doc.xref_set_key(page_xref,'Contents',_ref(stream));doc.xref_set_key(page_xref,'StructParents',str(key))
            doc.xref_set_key(page_xref,'Tabs','/S')
        else:
            doc.update_stream(stream_xref,payload);doc.xref_set_key(stream_xref,'StructParents',str(key))
        return children

    try:
        for index,page in enumerate(parsed.pages):
            px=doc[index].xref
            section=_new(doc,f'<< /Type /StructElem /S /Sect /P {_ref(document)} /Pg {_ref(px)} >>')
            sections.append(section)
            kids=process(page,None,px,section,page.obj.get('/Resources',{}),index)
            doc.xref_set_key(section,'K','['+' '.join(_ref(n) for n in kids)+']')
        nums=' '.join(f'{index} ['+' '.join(_ref(n) for n in nodes)+']' for index,nodes in enumerate(parents))
        tree=_new(doc,'<< /Nums ['+nums+'] >>')
        doc.xref_set_key(document,'K','['+' '.join(_ref(n) for n in sections)+']')
        doc.xref_set_key(root,'K',_ref(document));doc.xref_set_key(root,'ParentTree',_ref(tree));doc.xref_set_key(root,'ParentTreeNextKey',str(len(parents)))
        doc.xref_set_key(catalog,'StructTreeRoot',_ref(root));doc.xref_set_key(catalog,'MarkInfo','<< /Marked true >>')
        doc.xref_set_key(catalog,'Lang',fitz.get_pdf_str(language))
        doc.xref_set_key(catalog,'ViewerPreferences/DisplayDocTitle','true')
        metadata=doc.metadata;metadata['title']=title;doc.set_metadata(metadata)
        return count
    finally: parsed.close()
