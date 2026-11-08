"""PDF'e ve PDF'den dönüştürme araçları."""
from __future__ import annotations

import io
import re
import shutil
import tempfile
from pathlib import Path

import pymupdf as fitz

from .core import (SYSTEM, Job, Result, ToolError, find_browser, find_ghostscript, find_soffice,
                   has_ms_office, parse_pages, run, stem, zip_if_many)
from .pdf_tools import IMG, PDF, _add_image_page, _open_image, is_scanned, ocr_document, open_pdf, save

WORD = ["doc", "docx", "odt", "rtf", "txt"]
PPT = ["ppt", "pptx", "odp", "pps", "ppsx"]
XLS = ["xls", "xlsx", "ods", "csv"]


# =========================================================== PDF'E
def jpg_to_pdf(job: Job) -> Result:
    files = job.need(1, exts=IMG)
    size = job.opt("size", "a4")
    margin = {"none": 0, "small": 20, "big": 50}.get(job.opt("margin", "none"), 0)
    orient = job.opt("orientation", "auto")
    if job.flag("separate"):
        outs = []
        for f in files:
            d = fitz.open()
            _add_image_page(d, _open_image(f), size, margin, orient, quality=92)
            outs.append(save(d, job.path(f"{stem(f)}.pdf")))
        return Result(zip_if_many(job, outs, "gorseller_pdf.zip"))
    d = fitz.open()
    for f in files:
        _add_image_page(d, _open_image(f), size, margin, orient, quality=92)
    return Result([save(d, job.path(f"{stem(files[0])}.pdf" if len(files) == 1 else "gorseller.pdf"))])


def office_to_pdf(job: Job, kinds: list[str]) -> Result:
    files = job.need(1, exts=kinds)
    outs, notes = [], []
    for f in files:
        outs.append(convert_office(f, job.out, "pdf"))
    return Result(zip_if_many(job, outs, "pdfler.zip"), note="\n".join(notes) or None)


def word_to_pdf(job): return office_to_pdf(job, WORD)
def ppt_to_pdf(job): return office_to_pdf(job, PPT)
def excel_to_pdf(job): return office_to_pdf(job, XLS)


def convert_office(src: Path, outdir: Path, fmt: str = "pdf") -> Path:
    """Önce MS Office (Windows), sonra LibreOffice. Hiçbiri yoksa açık hata."""
    ext = src.suffix.lower().lstrip(".")
    target = outdir / f"{src.stem}.{fmt}"
    ms_err = None
    if SYSTEM == "Windows" and has_ms_office() and fmt == "pdf":
        try:
            _ms_office_to_pdf(src, target, ext)
            if target.exists():
                return target
        except Exception as e:  # Office açılamadıysa LibreOffice'e düş
            ms_err = e
    soffice = find_soffice()
    if soffice:
        with tempfile.TemporaryDirectory() as prof:
            prof_url = Path(prof).as_uri()
            r = run([soffice, f"-env:UserInstallation={prof_url}", "--headless", "--norestore",
                     "--convert-to", fmt, "--outdir", str(outdir), str(src)], timeout=300)
        if target.exists():
            return target
        raise ToolError(f"LibreOffice dönüştüremedi: {r.stderr.decode(errors='ignore')[:300]}")
    if ms_err:
        raise ToolError(f"Microsoft Office dönüştüremedi: {ms_err}")
    if ext == "txt" and fmt == "pdf":
        return _txt_to_pdf(src, target)
    if ext == "csv" and fmt == "pdf":
        return _txt_to_pdf(src, target, mono=True)
    raise ToolError("Ofis dosyalarını PDF'e çevirmek için Microsoft Office (Windows) ya da ücretsiz "
                    "LibreOffice gerekli. Ayarlar ekranındaki 'Ek bileşenler' bölümüne bakın.")


def _ms_office_to_pdf(src: Path, target: Path, ext: str):
    import pythoncom
    import win32com.client as win32
    pythoncom.CoInitialize()
    try:
        s, t = str(src.resolve()), str(target.resolve())
        if ext in WORD:
            app = win32.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            try:
                doc = app.Documents.Open(s, ReadOnly=True, AddToRecentFiles=False)
                doc.ExportAsFixedFormat(t, 17)  # wdExportFormatPDF
                doc.Close(False)
            finally:
                app.Quit()
        elif ext in PPT:
            app = win32.DispatchEx("PowerPoint.Application")
            try:
                pres = app.Presentations.Open(s, ReadOnly=True, WithWindow=False)
                pres.SaveAs(t, 32)  # ppSaveAsPDF
                pres.Close()
            finally:
                app.Quit()
        elif ext in XLS:
            app = win32.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            try:
                wb = app.Workbooks.Open(s, ReadOnly=True)
                wb.ExportAsFixedFormat(0, t)  # xlTypePDF
                wb.Close(False)
            finally:
                app.Quit()
    finally:
        pythoncom.CoUninitialize()


def _txt_to_pdf(src: Path, target: Path, mono=False) -> Path:
    import html as h
    text = src.read_text(encoding="utf-8", errors="replace")
    _story_to_pdf(tr_story(f"<pre>{h.escape(text)}</pre>", "pre{white-space:pre-wrap;font-size:9pt}"), target)
    return target


def tr_story(html_src: str, css: str = "") -> "fitz.Story":
    """Türkçe karakterli fontla HTML hikâyesi (PyMuPDF Story)."""
    from .core import unicode_font
    arch = fitz.Archive()
    arch.add(unicode_font(), "tr.ttf")
    arch.add(unicode_font(True), "trb.ttf")
    base = ("@font-face{font-family:tr;src:url(tr.ttf)}"
            "@font-face{font-family:tr;src:url(trb.ttf);font-weight:bold}"
            "*{font-family:tr} body{font-size:11pt}")
    return fitz.Story(html=html_src, user_css=base + css, archive=arch)


def _story_to_pdf(story, target: Path, page="a4", margin=40):
    mediabox = fitz.paper_rect(page)
    where = mediabox + (margin, margin, -margin, -margin)
    writer = fitz.DocumentWriter(str(target))
    more = 1
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()


def html_to_pdf(job: Job) -> Result:
    url = (job.opt("url") or "").strip()
    files = job.inputs
    if not url and not files:
        raise ToolError("Bir web adresi girin ya da HTML dosyası seçin.")
    if url and not re.match(r"^https?://", url):
        url = "https://" + url
    targets = [url] if url else [f.resolve().as_uri() for f in job.need(1, exts=["html", "htm", "mhtml"])]
    outs, used_fallback = [], False
    browser = find_browser()
    for t in targets:
        name = (re.sub(r"^https?://(www\.)?", "", t).split("/")[0] if url else Path(t).stem) or "sayfa"
        out = job.path(f"{name}.pdf")
        if browser:
            args = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
                    "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
                    f"--print-to-pdf={out}", "--virtual-time-budget=8000"]
            if not job.flag("header_footer"):
                args.append("--no-pdf-header-footer")
            try:
                with tempfile.TemporaryDirectory() as prof:
                    run(args + [f"--user-data-dir={prof}", t], timeout=90)
            except ToolError:
                pass   # tarayıcı takılırsa basit işleyiciye düş
        if not out.exists():   # tarayıcı yoksa: basit HTML işleyici
            used_fallback = True
            import requests
            src = requests.get(t, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).text if url else Path(
                files[0]).read_text(encoding="utf-8", errors="replace")
            src = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", "", src)
            _story_to_pdf(tr_story(src), out)
        outs.append(out)
    note = None if browser and not used_fallback else "Chrome/Edge kullanılamadı; sayfa sade biçimde dönüştürüldü."
    return Result(zip_if_many(job, outs, "web_pdf.zip"), note=note)


# =========================================================== PDF'DEN
def pdf_to_jpg(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    mode = job.opt("mode", "pages")
    fmt = job.opt("format", "jpg")
    dpi = int(job.num("dpi", 150))
    outs = []
    for f in files:
        doc = open_pdf(f)
        if mode == "extract":
            seen = set()
            for pg in doc:
                for img in pg.get_images(full=True):
                    xref = img[0]
                    if xref in seen:
                        continue
                    seen.add(xref)
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.n - pix.alpha >= 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        if pix.width < 32 or pix.height < 32:
                            continue
                        p = job.path(f"{stem(f)}_gorsel{len(seen)}.{'png' if pix.alpha or fmt == 'png' else 'jpg'}")
                        if p.suffix == ".jpg":
                            pix = fitz.Pixmap(pix, 0) if pix.alpha else pix
                            pix.save(p, jpg_quality=92)
                        else:
                            pix.save(p)
                        outs.append(p)
                    except Exception:
                        continue
            if not seen:
                raise ToolError(f"{f.name} içinde görsel bulunamadı.")
        else:
            pages = parse_pages(job.opt("pages"), doc.page_count)
            for i in pages:
                pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
                p = job.path(f"{stem(f)}_sayfa{i+1}.{fmt}")
                if fmt == "jpg":
                    pix.save(p, jpg_quality=int(job.num("quality", 90)))
                else:
                    pix.save(p)
                outs.append(p)
    return Result(zip_if_many(job, outs, "gorseller.zip"))


def pdf_to_word(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    from pdf2docx import Converter
    outs, notes = [], []
    for f in files:
        src = f
        doc = open_pdf(f)
        if job.flag("ocr", True) and is_scanned(doc):
            tmp = job.out / f"_{f.stem}_ocr.pdf"
            ocr_document(f).save(tmp)
            src = tmp
            notes.append(f"{f.name}: taranmış belge, önce OCR uygulandı.")
        p = job.path(f"{stem(f)}.docx")
        cv = Converter(str(src))
        try:
            cv.convert(str(p), start=0, end=None, multi_processing=False)
        finally:
            cv.close()
        if src != f:
            src.unlink(missing_ok=True)
        outs.append(p)
    return Result(zip_if_many(job, outs, "word.zip"), note="\n".join(notes) or None)


def pdf_to_ppt(job: Job) -> Result:
    """Her sayfa bir slayt: metinsiz arka plan görüntüsü + düzenlenebilir metin kutuları."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Emu, Pt
    files = job.need(1, exts=PDF)
    editable = job.opt("mode", "editable") == "editable"
    outs = []
    for f in files:
        doc = open_pdf(f)
        bg_doc = fitz.open(f)
        prs = Presentation()
        r0 = doc[0].rect
        k = 12700  # EMU / pt
        prs.slide_width, prs.slide_height = Emu(int(r0.width * k)), Emu(int(r0.height * k))
        blank = prs.slide_layouts[6]
        for pg in doc:
            slide = prs.slides.add_slide(blank)
            bpg = bg_doc[pg.number]
            if editable:   # metni görüntüden çıkar, kutu olarak ekle
                for b in bpg.get_text("dict")["blocks"]:
                    if b.get("type") == 0:
                        bpg.add_redact_annot(fitz.Rect(b["bbox"]))
                bpg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                     graphics=fitz.PDF_REDACT_LINE_ART_NONE, text=fitz.PDF_REDACT_TEXT_REMOVE)
            pix = bpg.get_pixmap(dpi=150, alpha=False)
            sx, sy = r0.width / pg.rect.width, r0.height / pg.rect.height
            slide.shapes.add_picture(io.BytesIO(pix.tobytes("png")), 0, 0,
                                     prs.slide_width, prs.slide_height)
            if not editable:
                continue
            for b in pg.get_text("dict")["blocks"]:
                if b.get("type") != 0:
                    continue
                x0, y0, x1, y1 = b["bbox"]
                tb = slide.shapes.add_textbox(Emu(int(x0 * sx * k)), Emu(int(y0 * sy * k)),
                                              Emu(int((x1 - x0) * sx * k) + k * 4), Emu(int((y1 - y0) * sy * k)))
                tf = tb.text_frame
                tf.word_wrap = True
                for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
                    setattr(tf, m, 0)
                first = True
                for line in b["lines"]:
                    para = tf.paragraphs[0] if first else tf.add_paragraph()
                    first = False
                    for sp in line["spans"]:
                        run_ = para.add_run()
                        run_.text = sp["text"]
                        run_.font.size = Pt(max(1, sp["size"] * sy))
                        c = sp["color"]
                        run_.font.color.rgb = RGBColor((c >> 16) & 255, (c >> 8) & 255, c & 255)
                        run_.font.bold = bool(sp["flags"] & 16)
                        run_.font.italic = bool(sp["flags"] & 2)
                        fam = re.sub(r"[-,].*$", "", sp["font"]).replace("MT", "")
                        if fam:
                            run_.font.name = fam
        p = job.path(f"{stem(f)}.pptx")
        prs.save(p)
        outs.append(p)
    return Result(zip_if_many(job, outs, "powerpoint.zip"))


def pdf_to_excel(job: Job) -> Result:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    files = job.need(1, exts=PDF)
    outs, notes = [], []
    one_sheet = job.opt("layout", "per_table") == "single"
    for f in files:
        doc = open_pdf(f)
        if is_scanned(doc) and job.flag("ocr", True):
            doc = ocr_document(f)
            notes.append(f"{f.name}: taranmış belge, önce OCR uygulandı.")
        wb = Workbook()
        wb.remove(wb.active)
        found = 0
        single = wb.create_sheet("Tablolar") if one_sheet else None
        row_ptr = 1
        for pg in doc:
            try:
                tabs = pg.find_tables().tables
            except Exception:
                tabs = []
            for t_i, t in enumerate(tabs, 1):
                data = [[" ".join(pg.get_text("text", clip=fitz.Rect(c)).split()) if c else None
                         for c in row.cells] for row in t.rows]
                if not data or not any(any(c for c in r) for r in data):
                    continue
                found += 1
                ws = single or wb.create_sheet(f"S{pg.number+1}_T{t_i}"[:31])
                start = row_ptr if single else 1
                if single:
                    ws.cell(start, 1, f"Sayfa {pg.number+1} · Tablo {t_i}").font = Font(bold=True, color="1F4E79")
                    start += 1
                for r_i, row in enumerate(data):
                    for c_i, val in enumerate(row):
                        cell = ws.cell(start + r_i, c_i + 1, _num(val))
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
                        if r_i == 0:
                            cell.font = Font(bold=True)
                            cell.fill = PatternFill("solid", fgColor="DDEBF7")
                if single:
                    row_ptr = start + len(data) + 1
                _autowidth(ws)
        if not found:   # tablo yoksa: satırları sütunlara böl
            ws = wb.create_sheet("Metin")
            r = 1
            for pg in doc:
                for line in pg.get_text("text", sort=True).splitlines():
                    if line.strip():
                        for c, val in enumerate(re.split(r"\s{2,}|\t", line.strip()), 1):
                            ws.cell(r, c, _num(val))
                        r += 1
            _autowidth(ws)
            notes.append(f"{f.name}: belirgin tablo bulunamadı; metin satır satır aktarıldı.")
        p = job.path(f"{stem(f)}.xlsx")
        wb.save(p)
        outs.append(p)
    return Result(zip_if_many(job, outs, "excel.zip"), note="\n".join(notes) or None)


def _num(v):
    if v is None:
        return None
    s = str(v).strip()
    t = s.replace(".", "").replace(",", ".") if re.fullmatch(r"-?\d{1,3}(\.\d{3})*(,\d+)?", s) else s
    try:
        if re.fullmatch(r"-?\d+", t):
            return int(t)
        if re.fullmatch(r"-?\d+\.\d+", t):
            return float(t)
    except ValueError:
        pass
    return s


def _autowidth(ws):
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(60, max(8, w + 2))


def pdf_to_pdfa(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    level = job.opt("level", "2b")
    gs = find_ghostscript()
    outs, note = [], None
    for f in files:
        p = job.path(f"{stem(f)}_PDFA-{level.upper()}.pdf")
        if gs:
            r = run([gs, f"-dPDFA={level[0]}", "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE",
                     "-sColorConversionStrategy=RGB", "-sProcessColorModel=DeviceRGB",
                     "-dPDFACompatibilityPolicy=1", "-sDEVICE=pdfwrite", f"-sOutputFile={p}", str(f)])
            if not p.exists():
                raise ToolError("Ghostscript dönüştüremedi: " + r.stderr.decode(errors="ignore")[:300])
            note = "Ghostscript ile PDF/A oluşturuldu."
        else:
            _pdfa_basic(f, p, level)
            note = ("Ghostscript yüklü olmadığı için temel PDF/A işaretleme yapıldı (fontlar gömülü, "
                    "sRGB çıktı profili, XMP). Resmî doğrulama (veraPDF) garanti değil; tam uyum için "
                    "Ghostscript kurun.")
        outs.append(p)
    return Result(zip_if_many(job, outs, "pdfa.zip"), note=note)


def _pdfa_basic(src: Path, dst: Path, level: str):
    import pikepdf
    from PIL import ImageCms
    tmp = dst.with_suffix(".tmp.pdf")
    d = fitz.open(src)
    d.scrub(javascript=True, embedded_files=True, attached_files=True, metadata=False,
            xml_metadata=False, thumbnails=True, reset_fields=False, reset_responses=False,
            clean_pages=False, hidden_text=False, redactions=False, remove_links=False)
    d.save(tmp, garbage=3, deflate=True)
    prof = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    with pikepdf.open(tmp) as pdf:
        icc = pikepdf.Stream(pdf, prof)
        icc["/N"] = 3
        pdf.Root.OutputIntents = pikepdf.Array([pikepdf.Dictionary(
            Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFA1,
            OutputConditionIdentifier="sRGB", Info="sRGB IEC61966-2.1", DestOutputProfile=icc)])
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta["pdfaid:part"] = level[0]
            meta["pdfaid:conformance"] = level[1:].upper() or "B"
            meta["dc:title"] = meta.get("dc:title") or src.stem
        pdf.save(dst)
    tmp.unlink(missing_ok=True)
