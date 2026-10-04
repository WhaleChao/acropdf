"""Local content edits with preflight checks and rollback on failure."""
import fitz


def _editable_page(document, page_num):
    page = document.fitz_doc[page_num]
    if any(annot.type[0] == fitz.PDF_ANNOT_REDACT for annot in page.annots() or ()):
        raise ValueError("此頁有待套用的塗黑標記，請先完成或刪除標記，再編輯內容。")
    return page


def replace_text_span(document, page_num, span, new_text):
    page = _editable_page(document, page_num)
    import math
    import uuid
    new_text = new_text.replace("\r\n", "\n").replace("\r", "\n")
    direction = span.get("direction", (1, 0))
    angle = round(math.degrees(math.atan2(-direction[1], direction[0]))) % 360
    fontsize = span["fontsize"]
    fontname = "china-t" if any(ord(c)>255 for c in new_text) else {0:"helv",2:"heit",16:"hebo",18:"hebi"}.get(span.get("flags",0)&18,"helv")
    font = fitz.Font(fontname=fontname)
    fontbuffer = None
    for item in page.get_fonts(full=True):
        if item[3].split("+")[-1].replace(" ","").lower() == span.get("font", "").replace(" ","").lower():
            try:
                buffer = document.fitz_doc.extract_font(item[0])[3]
                if buffer:
                    candidate = fitz.Font(fontbuffer=buffer)
                    if all(c.isspace() or candidate.has_glyph(ord(c)) for c in new_text):
                        fontbuffer = buffer; font = candidate; fontname = "acro_edit_"+uuid.uuid4().hex[:8]
            except Exception: pass
            break
    if any(not c.isspace() and not font.has_glyph(ord(c)) for c in new_text):
        raise ValueError("替換字型缺少所需字元，請先在字型管理選擇完整字型。")
    original = fitz.Rect(span["rect"]); target = fitz.Rect(original)
    multiline = "\n" in new_text
    if multiline:
        if angle != 0: raise ValueError("旋轉文字請逐行編輯，或先使用段落重排工具。")
        target.y1 = target.y0 + max(original.height, len(new_text.split("\n"))*fontsize*1.5+fontsize*.5)
        if not (page.rect*page.derotation_matrix).contains(target): raise ValueError("新段落超出頁面，原文已保留。")
        with fitz.open() as probe:
            p = probe.new_page(width=page.mediabox.width,height=page.mediabox.height)
            if fontbuffer: p.insert_font(fontname=fontname,fontbuffer=fontbuffer)
            if p.insert_textbox(target,new_text,fontsize=fontsize,fontname=fontname) < 0:
                raise ValueError("新段落超出可用區域，請縮短內容；原文已保留。")
    else:
        extent = original.width if angle in (0,180) else original.height if angle in (90,270) else math.hypot(original.width,original.height)
        if font.text_length(new_text,fontsize=fontsize) > extent + .5:
            raise ValueError("新文字超出原文字區域，請縮短內容；原文已保留。")
    # Redaction removes intersecting glyphs. Prevent loss of neighboring text.
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for other in line["spans"]:
                box = fitz.Rect(other["bbox"])
                if box == original: continue
                if box.intersects(original) or (multiline and box.intersects(target)):
                    raise ValueError("編輯區域與其他文字重疊，請先調整版面；原文已保留。")
    with document.edit_transaction("編輯文字"):
        page.add_redact_annot(original, fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_REMOVE)
        if fontbuffer: page.insert_font(fontname=fontname,fontbuffer=fontbuffer)
        if new_text:
            if multiline:
                result=page.insert_textbox(target,new_text,fontsize=fontsize,fontname=fontname,color=span["color"])
                if result<0: raise ValueError("段落重排失敗，已回復原文。")
            elif angle in (0,90,180,270):
                page.insert_text(span["origin"],new_text,fontsize=fontsize,fontname=fontname,color=span["color"],rotate=angle)
            else:
                matrix=fitz.Matrix(direction[0],direction[1],-direction[1],direction[0],0,0)
                page.insert_text(span["origin"],new_text,fontsize=fontsize,fontname=fontname,color=span["color"],morph=(span["origin"],matrix))


def replace_image_region(document, page_num, rect, *, filename=None, stream=None, new_rect=None):
    """Remove pixels in one placement without deleting overlaid text or vectors."""
    page = _editable_page(document, page_num)
    if filename is not None:
        fitz.Pixmap(filename)  # validate before removing any original content
    elif stream is not None:
        fitz.Pixmap(stream)
    with document.edit_transaction("編輯圖片"):
        page.add_redact_annot(rect, fill=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_NONE)
        if filename is not None or stream is not None:
            page.insert_image(new_rect or rect, filename=filename, stream=stream)
