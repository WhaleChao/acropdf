"""Offline standard-PDF conversion with mandatory independent PDF/A validation."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import fitz
from core.file_io import atomic_output


def find_executable(kind):
    configured = os.environ.get({'gs': 'ACROPDF_GHOSTSCRIPT', 'verapdf': 'ACROPDF_VERAPDF'}[kind])
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file(): return str(candidate)
        raise FileNotFoundError(f'設定的 {kind} 路徑不存在。')
    names = ['gs', 'gswin64c', 'gswin32c'] if kind == 'gs' else ['verapdf', 'verapdf.bat']
    for name in names:
        located = shutil.which(name)
        if located: return located
    root = Path(__file__).resolve().parents[1]
    candidates = ([Path('/opt/homebrew/bin/gs'), Path('/usr/local/bin/gs')] if kind == 'gs'
                  else [root / 'work/verapdf/verapdf'])
    if kind == 'gs' and os.name == 'nt':
        candidates.extend(Path(os.environ.get('ProgramFiles', 'C:/Program Files')).glob('gs/gs*/bin/gswin64c.exe'))
    for candidate in candidates:
        if candidate.is_file(): return str(candidate)
    raise RuntimeError(f'需要安裝 {"Ghostscript" if kind == "gs" else "veraPDF（含 Java）"}，請至依賴管理器設定。')


def _run(command, timeout=180, accepted_codes=(0,)):
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, **kwargs)
    if result.returncode not in accepted_codes:
        raise RuntimeError((result.stderr or result.stdout or '轉換程序失敗。')[-3000:])
    return result.stdout


def validate_pdfa(path, flavour='2b'):
    # veraPDF also returns 1 for a valid report containing non-compliance.
    raw = _run(validator_command() + ['--format', 'json', '--flavour', flavour, str(path)], accepted_codes=(0, 1))
    try:
        report = json.loads(raw)
        jobs = report['report']['jobs']
        result = jobs[0]['validationResult'][0]
        compliant = result.get('compliant') is True
        details = result['details']
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError('veraPDF 未回傳可判定的合規結果。') from exc
    if not compliant or details.get('failedChecks', 1) != 0:
        failures = [rule.get('description', '') for rule in details.get('ruleSummaries', []) if rule.get('ruleStatus') == 'FAILED']
        standard = 'PDF/UA' if flavour.startswith('ua') else 'PDF/A'
        raise ValueError(standard + ' 驗證未通過：' + '; '.join(failures[:4]))
    return report


def validator_command():
    if os.environ.get('ACROPDF_VERAPDF') or shutil.which('verapdf'):
        return [find_executable('verapdf')]
    root = Path(__file__).resolve().parents[1]
    jar = root / 'resources/validators/verapdf-cli-1.30.2.jar'
    java = find_java()
    bundled_java = root / 'resources/validators/java-runtime/bin' / ('java.exe' if os.name == 'nt' else 'java')
    if bundled_java.is_file(): java = str(bundled_java)
    if jar.is_file() and java:
        return [java, '-jar', str(jar)]
    return [find_executable('verapdf')]


def find_java():
    configured = os.environ.get('ACROPDF_JAVA')
    candidates = [configured] if configured else [shutil.which('java')]
    if os.name == 'nt':
        candidates.extend(Path(os.environ.get('ProgramFiles', 'C:/Program Files')).glob('Eclipse Adoptium/*/bin/java.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                result = subprocess.run([str(candidate), '-version'], capture_output=True, timeout=5,
                                        **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
                if result.returncode == 0: return str(candidate)
            except (OSError, subprocess.TimeoutExpired): pass
    return None


def _ps_string(text):
    return '(' + str(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ')'


class PDFStandards:
    def __init__(self, document): self.document = document

    def export_pdfua(self, output_path):
        """Publish only after independent PDF/UA-1 machine validation.

        Semantic reading order and adequacy of descriptions remain a human review.
        """
        import io
        import pikepdf
        from pikepdf.models.metadata import PdfMetadata
        from core.accessibility_engine import AccessibilityEngine
        if any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and w.is_signed for p in self.document.fitz_doc for w in p.widgets() or ()):
            raise ValueError('標準轉換會改寫已簽署內容，請使用未簽署的來源副本。')
        issues = AccessibilityEngine().validate_pdfua(self.document.fitz_doc)
        errors = [item['message'] for item in issues if item['severity'] == 'error']
        if errors: raise ValueError('\n'.join(errors))
        if self.document.is_encrypted: raise ValueError('請先另存未加密副本，再匯出 PDF/UA。')
        validator_command()
        PdfMetadata.register_xml_namespace('http://www.aiim.org/pdfua/ns/id/', 'pdfuaid')
        with atomic_output(output_path, source=self.document.source_path) as temporary:
            with pikepdf.open(io.BytesIO(self.document._snapshot())) as copied:
                # An omitted CIDToGIDMap has implicit Identity rendering semantics,
                # but PDF/UA requires the entry explicitly for embedded CIDFontType2.
                for obj in copied.objects:
                    if isinstance(obj, pikepdf.Dictionary) and obj.get('/Subtype') == pikepdf.Name('/CIDFontType2') and '/CIDToGIDMap' not in obj:
                        obj['/CIDToGIDMap'] = pikepdf.Name('/Identity')
                with copied.open_metadata(set_pikepdf_as_editor=False) as metadata:
                    metadata['pdfuaid:part'] = '1'
                    metadata['dc:title'] = self.document.fitz_doc.metadata['title']
                copied.save(temporary)
            report = validate_pdfa(temporary, 'ua1')
        return report

    def export_pdfa(self, output_path, flavour='2b', allow_decryption=False):
        if flavour not in ('1b', '2b', '3b'): raise ValueError('支援 PDF/A-1b、2b、3b。')
        if self.document.is_encrypted and not allow_decryption:
            raise ValueError('PDF/A 不允許加密，請明確同意輸出未加密副本。')
        gs = find_executable('gs'); validator_command()
        doc = self.document.fitz_doc
        if doc is None: raise ValueError('尚未載入文件。')
        if any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and w.is_signed for p in doc for w in p.widgets() or ()):
            raise ValueError('標準轉換會改寫已簽署內容，請使用未簽署的來源副本。')
        with atomic_output(output_path, source=self.document.source_path) as temporary, tempfile.TemporaryDirectory(prefix='acropdf_standard_') as stage:
            stage = Path(stage); source = stage / 'source.pdf'; icc = stage / 'sRGB.icc'
            # PDF/A-1 requires an ICC v2 output profile; LittleCMS's default is v4.
            bundled = Path(__file__).resolve().parents[1] / 'resources/color/sRGB2014.icc'
            shutil.copyfile(bundled, icc)
            # Save a fresh private clone: changing encryption on export must not alter the live document.
            with fitz.open('pdf', self.document._snapshot()) as copied:
                if copied.needs_pass and not copied.authenticate(self.document._password): raise ValueError('無法認證轉換快照。')
                copied.save(source, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
            definition = stage / 'definition.ps'
            definition.write_text(f'''%!
[/_objdef {{icc}} /type /stream /OBJ pdfmark
[{{icc}} << /N 3 >> /PUT pdfmark
[{{icc}} {_ps_string(icc)} (r) file /PUT pdfmark
[/_objdef {{intent}} /type /dict /OBJ pdfmark
[{{intent}} << /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {{icc}} /OutputConditionIdentifier (sRGB) >> /PUT pdfmark
[{{Catalog}} << /OutputIntents [{{intent}}] >> /PUT pdfmark
''')
            _run([gs, '-dSAFER', '-dBATCH', '-dNOPAUSE', '-dQUIET', f'-dPDFA={flavour[0]}',
                  '-dPDFACompatibilityPolicy=2', '-sDEVICE=pdfwrite', '-sColorConversionStrategy=RGB',
                  '-sBlendConversionStrategy=Managed', '-dEmbedAllFonts=true',
                  f'--permit-file-read={icc}', f'-sOutputICCProfile={icc}',
                  f'-sOutputFile={temporary}', str(definition), str(source)])
            with fitz.open(temporary) as result:
                if len(result) != len(doc): raise ValueError('轉換後頁數不符，未發佈輸出。')
            report = validate_pdfa(temporary, flavour)
        return report

    def export_pdfx(self, output_path, icc_path, level='4', allow_decryption=False):
        versions = {'1': 'PDF/X-1a:2001', '3': 'PDF/X-3:2002', '4': 'PDF/X-4'}
        if level not in versions: raise ValueError('支援 PDF/X-1a:2001、3:2002、4。')
        profile = Path(icc_path).resolve().read_bytes()
        if len(profile) < 128 or profile[36:40] != b'acsp' or profile[16:20] != b'CMYK':
            raise ValueError('請提供印刷廠指定的 CMYK ICC 描述檔。')
        if profile[12:16] != b'prtr': raise ValueError('ICC 必須是輸出裝置（prtr）描述檔。')
        if self.document.is_encrypted and not allow_decryption:
            raise ValueError('PDF/X 不允許加密，請明確同意輸出未加密副本。')
        doc = self.document.fitz_doc
        if doc is None: raise ValueError('尚未載入文件。')
        if any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and w.is_signed for p in doc for w in p.widgets() or ()):
            raise ValueError('標準轉換會改寫已簽署內容，請使用未簽署的來源副本。')
        gs = find_executable('gs')
        with atomic_output(output_path, source=self.document.source_path) as temporary, tempfile.TemporaryDirectory(prefix='acropdf_print_') as stage:
            stage = Path(stage); source = stage / 'source.pdf'; icc = stage / 'print.icc'
            icc.write_bytes(profile)
            with fitz.open('pdf', self.document._snapshot()) as copied:
                if copied.needs_pass and not copied.authenticate(self.document._password): raise ValueError('無法認證快照。')
                copied.save(source, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
            definition = stage / 'definition.ps'
            identifier = Path(icc_path).stem
            definition.write_text(f'''%!
[/GTS_PDFXVersion {_ps_string(versions[level])} /Title (AcroPDF print document) /Trapped /False /DOCINFO pdfmark
[/_objdef {{icc}} /type /stream /OBJ pdfmark
[{{icc}} << /N 4 >> /PUT pdfmark
[{{icc}} {_ps_string(icc)} (r) file /PUT pdfmark
[/_objdef {{intent}} /type /dict /OBJ pdfmark
[{{intent}} << /Type /OutputIntent /S /GTS_PDFX /DestOutputProfile {{icc}} /OutputConditionIdentifier {_ps_string(identifier)} /Info {_ps_string(identifier)} /RegistryName (http://www.color.org) >> /PUT pdfmark
[{{Catalog}} << /OutputIntents [{{intent}}] >> /PUT pdfmark
''', encoding='utf-8')
            _run([gs, '-dSAFER', '-dBATCH', '-dNOPAUSE', '-dQUIET', f'-dPDFX={level}',
                  '-dPDFXCompatibilityPolicy=2', '-sDEVICE=pdfwrite', '-sColorConversionStrategy=CMYK',
                  '-dEmbedAllFonts=true', f'--permit-file-read={icc}', f'-sOutputICCProfile={icc}',
                  f'-sOutputFile={temporary}', str(definition), str(source)])
            import pikepdf
            with pikepdf.open(temporary) as checked:
                if len(checked.pages) != len(doc) or checked.is_encrypted: raise ValueError('輸出頁數或加密狀態不符。')
                if str(checked.docinfo.get('/GTS_PDFXVersion', '')) != versions[level]: raise ValueError('轉換引擎未產生所選 PDF/X 等級。')
                intents = checked.Root.get('/OutputIntents', [])
                if not intents or intents[0].get('/S') != pikepdf.Name('/GTS_PDFX'):
                    raise ValueError('輸出缺少 PDF/X Output Intent。')
                if intents[0]['/DestOutputProfile'].read_bytes() != profile: raise ValueError('印刷 ICC 未完整嵌入。')
                for page in checked.pages:
                    if '/TrimBox' not in page.obj and '/ArtBox' not in page.obj: raise ValueError('輸出缺少裁切邊界。')
            with fitz.open(temporary) as checked:
                for page in checked:
                    page.get_pixmap(matrix=fitz.Matrix(.25,.25))
                    for font in page.get_fonts(full=True):
                        if font[0] <= 0 or not checked.extract_font(font[0])[3]: raise ValueError('輸出仍有未嵌入字型。')
        return {'level': versions[level], 'icc': identifier, 'page_count': len(doc),
                'checks': ['ICC bytes', 'output intent', 'page boxes', 'embedded fonts', 'page count', 'render'],
                'independent_pdfx_certification': False}
