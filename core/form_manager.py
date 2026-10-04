# ~/Desktop/acropdf/core/form_manager.py
import fitz

class FormManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def _safe_fitz(self) -> fitz.Document:
        doc = self._fitz
        if doc is None:
            raise RuntimeError("尚未載入文件")
        return doc

    def get_fields(self, page_num: int | None = None) -> list[dict]:
        """列出所有（或指定頁的）表單欄位"""
        doc = self._safe_fitz()
        results = []
        seen_radio_groups = set()
        pages = [page_num] if page_num is not None else range(doc.page_count)
        for i in pages:
            if i < 0 or i >= doc.page_count:
                continue
            page = self._fitz[i]
            for widget in page.widgets():
                value = widget.field_value
                if widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                    if widget.field_name in seen_radio_groups:
                        continue
                    seen_radio_groups.add(widget.field_name)
                    kind, reference = doc.xref_get_key(widget.xref, "Parent")
                    if kind == "xref":
                        value = doc.xref_get_key(int(reference.split()[0]), "V")[1].lstrip("/")
                results.append({
                    "page": i,
                    "field_name": widget.field_name,
                    "field_type": widget.field_type_string,
                    "field_value": value,
                    "rect": widget.rect,
                    "widget": widget,
                })
        return results

    def fill_field(self, page_num: int, field_name: str, value):
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("填寫欄位")
        page = doc[page_num]
        for widget in page.widgets():
            if widget.field_name == field_name:
                self._fill_widget(widget, value)
                break
        self._doc.end_op()
        self._doc._mark_modified()

    def fill_all(self, data: dict):
        """data: {field_name: value}"""
        doc = self._safe_fitz()
        self._doc.begin_op("批次填寫表單")
        for i in range(doc.page_count):
            page = doc[i]
            for widget in page.widgets():
                if widget.field_name in data:
                    self._fill_widget(widget, data[widget.field_name])
        self._doc.end_op()
        self._doc._mark_modified()

    def flatten_forms(self):
        """攤平：將表單值燒入頁面內容"""
        doc = self._safe_fitz()
        self._doc.begin_op("攤平表單")
        doc.bake(annots=False, widgets=True)
        self._doc.end_op()
        self._doc._mark_modified()

    def export_fdf(self, output_path: str):
        """Write a real FDF object graph, with escaped and Unicode PDF strings."""
        fields = []
        for field in self.get_fields():
            name = fitz.get_pdf_str(field["field_name"] or "")
            value = fitz.get_pdf_str(str(field["field_value"] or ""))
            fields.append(f"<< /T {name} /V {value} >>")
        header = b"%FDF-1.2\n"
        obj = ("1 0 obj\n<< /FDF << /Fields [" + " ".join(fields) + "] >> >>\nendobj\n").encode("ascii")
        offset = len(header) + len(obj)
        trailer = (f"xref\n0 2\n0000000000 65535 f \n{len(header):010d} 00000 n \n"
                   f"trailer\n<< /Root 1 0 R /Size 2 >>\nstartxref\n{offset}\n%%EOF\n").encode("ascii")
        with open(output_path, "wb") as handle:
            handle.write(header + obj + trailer)

    def import_fdf(self, fdf_path: str):
        from io import BytesIO
        from pypdf.generic import read_object
        content = open(fdf_path, "rb").read()
        marker = content.find(b"/Fields")
        if marker < 0:
            raise ValueError("FDF 中找不到欄位資料。")
        stream = BytesIO(content[marker + len(b"/Fields"):].lstrip())
        fields = read_object(stream, None)
        if not isinstance(fields, list):
            raise ValueError("FDF 欄位陣列不適用。")
        values = {str(field["/T"]): str(field.get("/V", "")) for field in fields}
        if values:
            self.fill_all(values)

    # ── 新增進階欄位 ──────────────────────────────────────────────
    @staticmethod
    def _pdf_name(value):
        return "/" + "".join(chr(b) if 33 <= b <= 126 and chr(b) not in "()<>[]{}/%#" else f"#{b:02X}"
                            for b in str(value).encode("utf-8"))

    def add_radio_button(self, page_num: int, rect: fitz.Rect, group_name: str, value: str):
        """Create a standard AcroForm radio parent and mutually exclusive children."""
        import re
        doc = self._safe_fitz()
        if not 0 <= page_num < doc.page_count or not group_name or not value or value == "Off":
            raise ValueError("請提供有效頁面、群組名稱與選項值（不能為 Off）。")
        for existing_page in doc:
            for existing in existing_page.widgets() or ():
                if existing.field_name == group_name:
                    if existing.field_type != fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                        raise ValueError("群組名稱已用於其他欄位。")
                    if existing.on_state() == value:
                        raise ValueError("群組選項值不能重複。")
        self._doc.begin_op("加選項按鈕")
        page = doc[page_num]
        widget = fitz.Widget()
        widget.rect = rect
        widget.field_name = group_name + "__" + value
        widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        widget.field_value = "Off"
        widget.fill_color = (1, 1, 1)
        widget.border_color = (0, 0, 0)
        widget.border_width = 1
        child = page.add_widget(widget).xref
        catalog = doc.pdf_catalog()
        fields = doc.xref_get_key(catalog, "AcroForm/Fields")[1]
        roots = [int(n) for n in re.findall(r"(\d+) 0 R", fields) if int(n) != child]
        parent = None
        for xref in roots:
            name = doc.xref_get_key(xref, "T")[1]
            flags = doc.xref_get_key(xref, "Ff")
            if name == group_name and flags[0] == "int" and int(flags[1]) & 32768:
                parent = xref
                break
        if parent is None:
            parent = doc.get_new_xref()
            doc.update_object(parent, f"<< /FT /Btn /T {fitz.get_pdf_str(group_name)} /Ff 32768 /V /Off /Kids [] >>")
            roots.append(parent)
        kids = [int(n) for n in re.findall(r"(\d+) 0 R", doc.xref_get_key(parent, "Kids")[1])]
        kids.append(child)
        doc.xref_set_key(parent, "Kids", "[" + " ".join(f"{n} 0 R" for n in kids) + "]")
        doc.xref_set_key(catalog, "AcroForm/Fields", "[" + " ".join(f"{n} 0 R" for n in roots) + "]")
        off = doc.xref_get_key(child, "AP/N/Off")[1]
        on = doc.xref_get_key(child, "AP/N/Yes")[1]
        state = self._pdf_name(value)
        doc.xref_set_key(child, "AP/N", f"<< /Off {off} {state} {on} >>")
        doc.xref_set_key(child, "Parent", f"{parent} 0 R")
        for key in ("T", "FT", "Ff", "V"):
            doc.xref_set_key(child, key, "null")
        # The next page load reads the updated field tree. Reloading a page
        # while widget wrappers still own it can fail in MuPDF on single-page PDFs.
        self._doc.end_op()
        self._doc._mark_modified()

    def _fill_widget(self, widget, value):
        if widget.field_type != fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
            widget.field_value = value
            widget.update()
            return
        import re
        doc = self._safe_fitz()
        kind, reference = doc.xref_get_key(widget.xref, "Parent")
        if kind != "xref":
            widget.field_value = value
            widget.update()
            return
        parent = int(reference.split()[0])
        kids = [int(n) for n in re.findall(r"(\d+) 0 R", doc.xref_get_key(parent, "Kids")[1])]
        state = self._pdf_name(value)
        active = None
        for child in kids:
            if doc.xref_get_key(child, "AP/N/" + state[1:])[0] == "xref":
                active = child
                break
        if active is None and str(value) not in ("Off", ""):
            raise ValueError(f"選項值不在群組中：{value}")
        for child in kids:
            doc.xref_set_key(child, "AS", state if child == active else "/Off")
        doc.xref_set_key(parent, "V", state if active is not None else "/Off")

    def add_push_button(self, page_num: int, rect: fitz.Rect,
                        name: str, caption: str):
        """新增按鈕"""
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("加按鈕")
        page = doc[page_num]
        widget = fitz.Widget()
        widget.rect = rect
        widget.field_name = name
        widget.field_type = fitz.PDF_WIDGET_TYPE_BUTTON
        widget.field_value = caption
        widget.text_fontsize = 11
        widget.fill_color = (0.9, 0.9, 0.9)
        widget.border_color = (0, 0, 0)
        widget.border_width = 1
        page.add_widget(widget)
        self._doc.end_op()
        self._doc._mark_modified()

    def add_signature_field(self, page_num: int, rect: fitz.Rect, name: str):
        """新增簽名欄位"""
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("加簽名欄位")
        page = doc[page_num]
        widget = fitz.Widget()
        widget.rect = rect
        widget.field_name = name
        widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
        widget.fill_color = (1, 1, 1)
        widget.border_color = (0, 0, 0.8)
        widget.border_width = 1
        page.add_widget(widget)
        self._doc.end_op()
        self._doc._mark_modified()

    def set_field_properties(self, page_num: int, field_name: str,
                             properties: dict):
        """設定欄位屬性（字型、邊框、顏色、旗標）"""
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("設定欄位屬性")
        page = doc[page_num]
        for widget in page.widgets():
            if widget.field_name == field_name:
                if "font_size" in properties:
                    widget.text_fontsize = properties["font_size"]
                if "fill_color" in properties:
                    widget.fill_color = properties["fill_color"]
                if "border_color" in properties:
                    widget.border_color = properties["border_color"]
                if "border_width" in properties:
                    widget.border_width = properties["border_width"]
                if "text_color" in properties:
                    widget.text_color = properties["text_color"]
                if "field_value" in properties:
                    widget.field_value = properties["field_value"]
                widget.update()
                break
        self._doc.end_op()
        self._doc._mark_modified()

    def set_tab_order(self, page_num: int, field_names: list[str]):
        """Order widget annotations explicitly using PDF 2.0 widget tab order."""
        import re
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            raise ValueError("頁碼無效。")
        page = doc[page_num]
        groups = {}
        for widget in page.widgets() or ():
            groups.setdefault(widget.field_name, []).append(widget.xref)
        if len(field_names) != len(set(field_names)) or set(field_names) != set(groups):
            raise ValueError("Tab 順序必須包含此頁每個欄位名稱恰好一次。")
        annotations = [int(n) for n in re.findall(r"(\d+) 0 R", doc.xref_get_key(page.xref, "Annots")[1])]
        widgets = {xref for group in groups.values() for xref in group}
        order = [xref for name in field_names for xref in groups[name]]
        order.extend(xref for xref in annotations if xref not in widgets)
        with self._doc.edit_transaction("表單 Tab 順序"):
            doc.xref_set_key(page.xref, "Annots", "[" + " ".join(f"{xref} 0 R" for xref in order) + "]")
            doc.xref_set_key(page.xref, "Tabs", "/W")
            doc.xref_set_key(doc.pdf_catalog(), "Version", "/2.0")

    def get_all_fields(self, page_num: int | None = None) -> list[dict]:
        """取得所有欄位資訊（含座標、類型、屬性）"""
        doc = self._safe_fitz()
        results = []
        pages = [page_num] if page_num is not None else range(doc.page_count)
        for i in pages:
            if i < 0 or i >= doc.page_count:
                continue
            for widget in doc[i].widgets():
                results.append({
                    "page": i,
                    "name": widget.field_name,
                    "type": widget.field_type_string,
                    "value": widget.field_value,
                    "rect": widget.rect,
                    "font_size": widget.text_fontsize,
                    "fill_color": widget.fill_color,
                    "border_color": widget.border_color,
                })
        return results

    # ── 新增欄位 ──────────────────────────────────────────────────
    def add_field(self, page_num: int, rect: fitz.Rect,
                  field_type: str, name: str, default_value: str = ""):
        """
        field_type: 'text' | 'checkbox' | 'combo' | 'list'
        """
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        if not name:
            name = f"field_{page_num}_{id(rect)}"
        self._doc.begin_op("加表單欄位")
        page = doc[page_num]
        widget = fitz.Widget()
        widget.rect = rect
        widget.field_name = name
        _type_map = {
            "text":     fitz.PDF_WIDGET_TYPE_TEXT,
            "checkbox": fitz.PDF_WIDGET_TYPE_CHECKBOX,
            "combo":    fitz.PDF_WIDGET_TYPE_COMBOBOX,
            "list":     fitz.PDF_WIDGET_TYPE_LISTBOX,
        }
        widget.field_type = _type_map.get(field_type, fitz.PDF_WIDGET_TYPE_TEXT)
        if field_type == "checkbox":
            widget.field_value = bool(default_value)
        else:
            widget.field_value = default_value
        widget.text_fontsize = 11
        widget.text_color = (0, 0, 0)
        widget.fill_color = (1, 1, 1)
        widget.border_color = (0, 0, 0)
        widget.border_width = 1
        page.add_widget(widget)
        self._doc.end_op()
        self._doc._mark_modified()
