"""PDF düzenleme, optimizasyon, güvenlik araçları (PyMuPDF + pikepdf)."""
from __future__ import annotations

import base64
import difflib
import html
import io
import re
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageOps, ImageFilter

from .core import (Job, Result, ToolError, add_font, hex_to_rgb, parse_pages, parse_ranges,
                   stem, tessdata_dir, text_width, zip_if_many)

PDF = ["pdf"]
IMG = ["jpg", "jpeg", "png", "bmp", "gif", "tif", "tiff", "webp", "heic"]


def open_pdf(path: Path, password: str | None = None) -> fitz.Document:
    try:
        doc = fitz.open(path)
    except Exception as e:
        raise ToolError(f"{path.name} açılamadı (bozuk olabilir, 'PDF onar' aracını deneyin): {e}")
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            raise ToolError(f"{path.name} parola korumalı. Önce 'PDF kilidini aç' aracını kullanın.")
    return doc


def save(doc: fitz.Document, path: Path, compact=True) -> Path:
    doc.save(path, garbage=3 if compact else 0, deflate=True)
    return path


# =========================================================== DÜZENLE
def merge(job: Job) -> Result:
    files = job.need(2, exts=PDF + IMG)
    out = fitz.open()
    for f in files:
        if f.suffix.lower() == ".pdf":
            out.insert_pdf(open_pdf(f))
        else:
            img = fitz.open(f)
            out.insert_pdf(fitz.open("pdf", img.convert_to_pdf()))
    if job.flag("bookmarks", True):
        toc, pos = [], 1
        for f in files:
            n = fitz.open(f).page_count if f.suffix.lower() == ".pdf" else 1
            toc.append([1, stem(f), pos])
            pos += n
        out.set_toc(toc)
    return Result([save(out, job.path("birlestirilmis.pdf"))])


def split(job: Job) -> Result:
    (f,) = job.need(1, 1, PDF)
    doc = open_pdf(f)
    mode = job.opt("mode", "ranges")
    n = doc.page_count
    if mode == "all":
        groups = [[i] for i in range(n)]
    elif mode == "every":
        k = max(1, int(job.num("every", 1)))
        groups = [list(range(i, min(i + k, n))) for i in range(0, n, k)]
    elif mode == "size":
        return _split_by_size(job, doc, f)
    else:
        groups = parse_ranges(job.opt("ranges", "1"), n)
    if job.flag("merge_ranges") and mode == "ranges":
        nd = fitz.open()
        for g in groups:
            for p in g:
                nd.insert_pdf(doc, from_page=p, to_page=p)
        return Result([save(nd, job.path(f"{stem(f)}_secilen.pdf"))])
    outs = []
    for g in groups:
        nd = fitz.open()
        for p in g:
            nd.insert_pdf(doc, from_page=p, to_page=p)
        label = f"{g[0]+1}" if len(g) == 1 else f"{g[0]+1}-{g[-1]+1}"
        outs.append(save(nd, job.path(f"{stem(f)}_s{label}.pdf")))
    return Result(zip_if_many(job, outs, f"{stem(f)}_bolunmus.zip"))


def _split_by_size(job: Job, doc, f) -> Result:
    limit = job.num("max_mb", 5) * 1024 * 1024

    def build(pages):
        nd = fitz.open()
        for p in pages:
            nd.insert_pdf(doc, from_page=p, to_page=p)
        return nd

    groups, cur = [], []
    for i in range(doc.page_count):
        if cur and len(build(cur + [i]).tobytes(garbage=3, deflate=True)) > limit:
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    outs = [save(build(g), job.path(f"{stem(f)}_s{g[0]+1}-{g[-1]+1}.pdf")) for g in groups]
    return Result(zip_if_many(job, outs, f"{stem(f)}_bolunmus.zip"))


def remove_pages(job: Job) -> Result:
    (f,) = job.need(1, 1, PDF)
    doc = open_pdf(f)
    pages = parse_pages(job.opt("pages"), doc.page_count, default_all=False)
    if not pages:
        raise ToolError("Silinecek sayfaları girin. Örnek: 2, 5-7")
    if len(pages) >= doc.page_count:
        raise ToolError("Tüm sayfaları silemezsiniz.")
    doc.delete_pages(sorted(pages))
    return Result([save(doc, job.path(f"{stem(f)}_sayfalar_silindi.pdf"))])


def extract_pages(job: Job) -> Result:
    (f,) = job.need(1, 1, PDF)
    doc = open_pdf(f)
    pages = parse_pages(job.opt("pages"), doc.page_count, default_all=False)
    if not pages:
        raise ToolError("Ayıklanacak sayfaları girin. Örnek: 1, 3-4")
    if job.flag("separate"):
        outs = []
        for p in pages:
            nd = fitz.open()
            nd.insert_pdf(doc, from_page=p, to_page=p)
            outs.append(save(nd, job.path(f"{stem(f)}_sayfa{p+1}.pdf")))
        return Result(zip_if_many(job, outs, f"{stem(f)}_sayfalar.zip"))
    doc.select(sorted(pages))
    return Result([save(doc, job.path(f"{stem(f)}_ayiklanan.pdf"))])


def organize(job: Job) -> Result:
    """opts.layout = [{"f":dosya_no,"p":sayfa_no,"r":derece} | {"blank":true}] (sıra = yeni sıra)."""
    files = job.need(1, exts=PDF)
    docs = [open_pdf(f) for f in files]
    layout = job.opts.get("layout")
    if not layout:   # arayüz göndermediyse: tüm sayfalar sırayla
        layout = [{"f": i, "p": p, "r": 0} for i, d in enumerate(docs) for p in range(d.page_count)]
    out = fitz.open()
    for item in layout:
        if item.get("blank"):
            ref = out[-1].rect if out.page_count else fitz.paper_rect("a4")
            out.new_page(width=ref.width, height=ref.height)
            continue
        d = docs[int(item.get("f", 0))]
        p = int(item["p"])
        out.insert_pdf(d, from_page=p, to_page=p)
        r = int(item.get("r", 0)) % 360
        if r:
            pg = out[-1]
            pg.set_rotation((pg.rotation + r) % 360)
    if not out.page_count:
        raise ToolError("Hiç sayfa kalmadı.")
    return Result([save(out, job.path(f"{stem(files[0])}_duzenlenmis.pdf"))])


def scan_to_pdf(job: Job) -> Result:
    """Telefon/kamera fotoğraflarını belge görünümüne getirip PDF yapar."""
    files = job.need(1, exts=IMG)
    mode = job.opt("filter", "auto")
    out = fitz.open()
    for f in files:
        im = _open_image(f)
        if job.flag("auto_crop", True):
            im = _auto_crop_document(im)
        if mode in ("auto", "gray", "bw"):
            g = ImageOps.grayscale(im)
            g = ImageOps.autocontrast(g, cutoff=2)
            if mode == "bw":
                g = g.filter(ImageFilter.MedianFilter(3)).point(lambda v: 255 if v > 150 else 0, "1")
            elif mode == "auto":
                g = g.filter(ImageFilter.SHARPEN)
            im = g
        elif mode == "color":
            im = ImageOps.autocontrast(im.convert("RGB"), cutoff=1)
        _add_image_page(out, im, "a4", 0, quality=80)
    return Result([save(out, job.path("taranan_belge.pdf"))])


def _open_image(f: Path) -> Image.Image:
    try:
        if f.suffix.lower() == ".heic":
            try:
                import pillow_heif  # type: ignore
                pillow_heif.register_heif_opener()
            except ImportError:
                raise ToolError("HEIC için 'pillow-heif' paketi gerekli. Fotoğrafı JPG olarak kaydedin.")
        im = Image.open(f)
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, "white")
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        return im.convert("RGB") if im.mode not in ("RGB", "L") else im
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(f"{f.name} görsel olarak açılamadı: {e}")


def _auto_crop_document(im: Image.Image) -> Image.Image:
    """Kâğıdı arka plandan ayırıp perspektif düzeltir (OpenCV varsa)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return im
    arr = np.array(im.convert("RGB"))
    h, w = arr.shape[:2]
    scale = 800 / max(h, w)
    small = cv2.resize(arr, (int(w * scale), int(h * scale)))
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), None, iterations=2)
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:5]:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.contourArea(approx) > 0.25 * small.shape[0] * small.shape[1]:
            pts = approx.reshape(4, 2).astype("float32") / scale
            s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
            tl, br, tr, bl = pts[s.argmin()], pts[s.argmax()], pts[d.argmin()], pts[d.argmax()]
            W = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
            H = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
            M = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl]),
                                            np.array([[0, 0], [W, 0], [W, H], [0, H]], "float32"))
            return Image.fromarray(cv2.warpPerspective(arr, M, (W, H)))
    return im


def _add_image_page(out: fitz.Document, im: Image.Image, size: str, margin: float,
                    orientation="auto", quality=85):
    buf = io.BytesIO()
    if im.mode == "1":
        im.save(buf, "PNG", optimize=True)
    else:
        im.save(buf, "JPEG", quality=quality, optimize=True)
    iw, ih = im.size
    if size == "fit":
        dpi = (im.info.get("dpi") or (96, 96))[0] or 96
        pw, ph = iw * 72 / dpi + 2 * margin, ih * 72 / dpi + 2 * margin
    else:
        r = fitz.paper_rect(size)
        pw, ph = r.width, r.height
        land = orientation == "landscape" or (orientation == "auto" and iw > ih)
        if land:
            pw, ph = ph, pw
    page = out.new_page(width=pw, height=ph)
    page.insert_image(fitz.Rect(margin, margin, pw - margin, ph - margin),
                      stream=buf.getvalue(), keep_proportion=True)


# =========================================================== OPTİMİZE
COMPRESS = {   # dpi eşiği, hedef dpi, jpeg kalitesi
    "low": (200, 150, 85),
    "recommended": (150, 110, 70),
    "extreme": (96, 72, 45),
}


def compress(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    level = job.opt("level", "recommended")
    th, target, q = COMPRESS.get(level, COMPRESS["recommended"])
    outs, notes = [], []
    for f in files:
        doc = open_pdf(f)
        try:
            doc.rewrite_images(dpi_threshold=th, dpi_target=target, quality=q,
                               lossy=True, lossless=True, bitonal=True, color=True, gray=True,
                               set_to_gray=job.flag("grayscale"))
        except Exception as e:  # bazı görseller yeniden yazılamayabilir
            notes.append(f"{f.name}: bazı görseller atlandı ({e})")
        try:
            doc.subset_fonts()
        except Exception:
            pass
        doc.scrub(metadata=False, xml_metadata=False, attached_files=False, embedded_files=False,
                  thumbnails=True, reset_fields=False, reset_responses=False, javascript=False,
                  clean_pages=True, hidden_text=False, redactions=False, remove_links=False)
        p = job.path(f"{stem(f)}_kucultulmus.pdf")
        doc.save(p, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
                 use_objstms=1, clean=True)
        a, b = f.stat().st_size, p.stat().st_size
        if b >= a:   # küçülmediyse orijinali koru
            p.write_bytes(f.read_bytes())
            b = a
            notes.append(f"{f.name}: zaten optimize, daha fazla küçülmedi.")
        else:
            notes.append(f"{f.name}: {a/1024/1024:.2f} MB → {b/1024/1024:.2f} MB (%{100*(a-b)/a:.0f} küçüldü)")
        outs.append(p)
    return Result(zip_if_many(job, outs, "kucultulmus_pdfler.zip"), note="\n".join(notes))


def repair(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    outs, notes = [], []
    for f in files:
        p = job.path(f"{stem(f)}_onarilmis.pdf")
        ok = False
        try:
            import pikepdf
            with pikepdf.open(f, attempt_recovery=True) as pdf:
                pdf.save(p)
            fitz.open(p).page_count
            ok = True
            notes.append(f"{f.name}: qpdf ile onarıldı.")
        except Exception as e1:
            try:
                doc = fitz.open(f)
                doc.save(p, garbage=4, deflate=True, clean=True)
                ok = True
                notes.append(f"{f.name}: MuPDF ile yeniden yazıldı ({e1}).")
            except Exception as e2:
                notes.append(f"{f.name}: onarılamadı — {e2}")
        if ok:
            outs.append(p)
    if not outs:
        raise ToolError("\n".join(notes))
    return Result(zip_if_many(job, outs, "onarilmis.zip"), note="\n".join(notes))


OCR_LANGS = {"tur": "Türkçe", "eng": "İngilizce", "deu": "Almanca", "fra": "Fransızca",
             "spa": "İspanyolca", "ita": "İtalyanca", "rus": "Rusça", "ara": "Arapça"}


def ocr(job: Job) -> Result:
    files = job.need(1, exts=PDF + IMG)
    langs = [l for l in re.split(r"[+,\s]+", job.opt("lang", "tur+eng")) if l]
    tess = tessdata_dir(langs)
    dpi = int(job.num("dpi", 300))
    outs = []
    for f in files:
        out = fitz.open()
        src = fitz.open(f) if f.suffix.lower() == ".pdf" else None
        pages = src if src is not None else [None]
        for page in pages:
            if page is None:
                pix = fitz.Pixmap(str(f))
                if pix.alpha:
                    pix = fitz.Pixmap(pix, 0)
            else:
                if job.flag("skip_text", True) and len(page.get_text().strip()) > 50:
                    out.insert_pdf(src, from_page=page.number, to_page=page.number)
                    continue
                pix = page.get_pixmap(dpi=dpi)
            data = pix.pdfocr_tobytes(language="+".join(langs), tessdata=tess)
            out.insert_pdf(fitz.open("pdf", data))
        outs.append(save(out, job.path(f"{stem(f)}_ocr.pdf")))
    return Result(zip_if_many(job, outs, "ocr.zip"),
                  note="Metin artık seçilebilir ve aranabilir (görünüm aynı kalır).")


def ocr_document(path: Path, langs=("tur", "eng"), dpi=300) -> fitz.Document:
    """Diğer araçlar için: taranmış PDF'e metin katmanı ekleyip döner."""
    tess = tessdata_dir(list(langs))
    src = fitz.open(path)
    out = fitz.open()
    for page in src:
        if len(page.get_text().strip()) > 50:
            out.insert_pdf(src, from_page=page.number, to_page=page.number)
            continue
        pix = page.get_pixmap(dpi=dpi)
        out.insert_pdf(fitz.open("pdf", pix.pdfocr_tobytes(language="+".join(langs), tessdata=tess)))
    return out


def is_scanned(doc: fitz.Document) -> bool:
    n = min(doc.page_count, 5)
    return n > 0 and sum(len(doc[i].get_text().strip()) for i in range(n)) < 30 * n


# =========================================================== DÜZENLE (EDIT)
def rotate(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    angle = int(job.num("angle", 90))
    outs = []
    for f in files:
        doc = open_pdf(f)
        which = job.opt("which", "all")
        pages = range(doc.page_count)
        if which == "odd":
            pages = range(0, doc.page_count, 2)
        elif which == "even":
            pages = range(1, doc.page_count, 2)
        elif which == "custom":
            pages = parse_pages(job.opt("pages"), doc.page_count)
        for i in pages:
            pg = doc[i]
            pg.set_rotation((pg.rotation + angle) % 360)
        outs.append(save(doc, job.path(f"{stem(f)}_dondurulmus.pdf")))
    return Result(zip_if_many(job, outs, "dondurulmus.zip"))


POS = {"tl": (0, 0), "tc": (1, 0), "tr": (2, 0), "ml": (0, 1), "mc": (1, 1), "mr": (2, 1),
       "bl": (0, 2), "bc": (1, 2), "br": (2, 2)}


def _anchor(rect: fitz.Rect, pos: str, w: float, h: float, margin: float) -> fitz.Point:
    cx, cy = POS.get(pos, (1, 2))
    x = [rect.x0 + margin, rect.x0 + (rect.width - w) / 2, rect.x1 - margin - w][cx]
    y = [rect.y0 + margin + h, rect.y0 + (rect.height + h) / 2, rect.y1 - margin][cy]
    return fitz.Point(x, y)


def page_numbers(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    outs = []
    for f in files:
        doc = open_pdf(f)
        total = doc.page_count
        pages = parse_pages(job.opt("pages"), total)
        start = int(job.num("start", 1))
        fmt = job.opt("format", "{n}")
        size = job.num("size", 11)
        color = hex_to_rgb(job.opt("color", "#000000"))
        margin = job.num("margin", 28)
        pos = job.opt("position", "bc")
        facing = job.flag("facing")
        for k, i in enumerate(pages):
            pg = doc[i]
            n = start + k
            txt = (fmt.replace("{n}", str(n)).replace("{total}", str(start + len(pages) - 1))
                   .replace("{p}", str(i + 1)))
            p = pos
            if facing and k % 2 == 1:   # çift sayfa: konumu aynala
                p = p.replace("r", "§").replace("l", "r").replace("§", "l")
            w = text_width(txt, size)
            fn = add_font(pg)
            rect = pg.rect
            pt = _anchor(rect, p, w, size * 0.75, margin)
            pt = pt * pg.derotation_matrix
            pg.insert_text(pt, txt, fontsize=size, fontname=fn, color=color, rotate=pg.rotation)
        outs.append(save(doc, job.path(f"{stem(f)}_numarali.pdf")))
    return Result(zip_if_many(job, outs, "numarali.zip"))


def watermark(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    kind = job.opt("kind", "text")
    opacity = max(0.05, min(1.0, job.num("opacity", 30) / 100))
    angle = job.num("angle", 45)
    pos = job.opt("position", "mc")
    mosaic = job.flag("mosaic")
    below = job.opt("layer", "over") == "under"
    img_path = job.extra.get("image")
    if kind == "image" and not img_path:
        raise ToolError("Filigran görseli seçin.")
    outs = []
    for f in files:
        doc = open_pdf(f)
        pages = parse_pages(job.opt("pages"), doc.page_count)
        for i in pages:
            pg = doc[i]
            if kind == "image":
                _wm_image(pg, img_path, opacity, pos, job.num("scale", 40) / 100, mosaic, below)
            else:
                _wm_text(pg, job.opt("text", "GİZLİ"), job.num("size", 60),
                         hex_to_rgb(job.opt("color", "#d32f2f")), opacity, angle, pos, mosaic,
                         job.flag("bold", True), below)
        outs.append(save(doc, job.path(f"{stem(f)}_filigranli.pdf")))
    return Result(zip_if_many(job, outs, "filigranli.zip"))


def _wm_text(pg, text, size, color, opacity, angle, pos, mosaic, bold, below):
    fn = add_font(pg, bold)
    w = text_width(text, size, bold)
    rect = pg.rect
    points = []
    if mosaic:
        step_x, step_y = w + size * 2, size * 4
        y = rect.y0 + size
        while y < rect.y1 + size:
            x = rect.x0 - w / 2
            while x < rect.x1:
                points.append(fitz.Point(x + w / 2, y))
                x += step_x
            y += step_y
    else:
        cx, cy = POS.get(pos, (1, 1))
        m = 36
        x = [rect.x0 + m + w / 2, rect.x0 + rect.width / 2, rect.x1 - m - w / 2][cx]
        y = [rect.y0 + m + size, rect.y0 + rect.height / 2, rect.y1 - m - size][cy]
        points.append(fitz.Point(x, y))
    for c in points:   # c: metnin merkezi
        c = c * pg.derotation_matrix
        start = fitz.Point(c.x - w / 2, c.y + size * 0.35)
        mat = fitz.Matrix(-angle - pg.rotation)
        pg.insert_text(start, text, fontsize=size, fontname=fn, color=color,
                       fill_opacity=opacity, stroke_opacity=opacity, morph=(c, mat),
                       overlay=not below)


def _wm_image(pg, img_path, opacity, pos, scale, mosaic, below):
    im = Image.open(img_path).convert("RGBA")
    a = im.split()[-1].point(lambda v: int(v * opacity))
    im.putalpha(a)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    data = buf.getvalue()
    rect = pg.rect
    w = rect.width * scale
    h = w * im.height / im.width
    rects = []
    if mosaic:
        y = rect.y0
        while y < rect.y1:
            x = rect.x0
            while x < rect.x1:
                rects.append(fitz.Rect(x, y, x + w, y + h))
                x += w * 1.4
            y += h * 1.6
    else:
        cx, cy = POS.get(pos, (1, 1))
        m = 36
        x = [rect.x0 + m, rect.x0 + (rect.width - w) / 2, rect.x1 - m - w][cx]
        y = [rect.y0 + m, rect.y0 + (rect.height - h) / 2, rect.y1 - m - h][cy]
        rects.append(fitz.Rect(x, y, x + w, y + h))
    for r in rects:
        pg.insert_image(r * pg.derotation_matrix, stream=data, overlay=not below,
                        rotate=-pg.rotation % 360 if pg.rotation else 0)


def crop(job: Job) -> Result:
    (f,) = job.need(1, 1, PDF)
    doc = open_pdf(f)
    box = job.opts.get("box")         # arayüzde seçilen alan (görünür sayfa koordinatı, nokta)
    mm = 72 / 25.4
    which = job.opt("which", "all")
    pages = range(doc.page_count) if which == "all" else parse_pages(job.opt("pages"), doc.page_count)
    for i in pages:
        pg = doc[i]
        vis = pg.rect
        if box:
            r = fitz.Rect(box["x0"], box["y0"], box["x1"], box["y1"]) & vis
        else:
            r = fitz.Rect(vis.x0 + job.num("left", 10) * mm, vis.y0 + job.num("top", 10) * mm,
                          vis.x1 - job.num("right", 10) * mm, vis.y1 - job.num("bottom", 10) * mm)
        if r.is_empty or r.width < 20 or r.height < 20:
            raise ToolError("Kırpma alanı çok küçük.")
        unrot = r * pg.derotation_matrix
        unrot.normalize()
        mb = pg.mediabox
        cb = fitz.Rect(unrot.x0 + mb.x0, unrot.y0 + mb.y0, unrot.x1 + mb.x0, unrot.y1 + mb.y0) & mb
        pg.set_cropbox(fitz.Rect(cb.x0 - mb.x0, cb.y0 - mb.y0, cb.x1 - mb.x0, cb.y1 - mb.y0))
    return Result([save(doc, job.path(f"{stem(f)}_kirpilmis.pdf"))])


def edit(job: Job) -> Result:
    """opts.items: [{type:'text'|'image'|'rect'|'ellipse'|'line'|'ink'|'highlight'|'whiteout', page, ...}]
    Koordinatlar görünür sayfa üzerinde PDF noktası (sol üst köşe 0,0)."""
    (f,) = job.need(1, 1, PDF)
    doc = open_pdf(f)
    items = job.opts.get("items") or []
    if not items:
        raise ToolError("Sayfaya en az bir öğe ekleyin (metin, şekil, görsel, çizim).")
    for it in items:
        _draw_item(doc[int(it.get("page", 0))], it, job)
    return Result([save(doc, job.path(f"{stem(f)}_duzenlendi.pdf"))])


def _draw_item(pg, it: dict, job: Job):
    t = it.get("type")
    dm = pg.derotation_matrix
    color = hex_to_rgb(it.get("color"), (0, 0, 0))
    fill = hex_to_rgb(it["fill"]) if it.get("fill") else None
    opacity = float(it.get("opacity", 1))
    width = float(it.get("width", 2))
    r = fitz.Rect(it.get("x", 0), it.get("y", 0),
                  it.get("x", 0) + it.get("w", 0), it.get("y", 0) + it.get("h", 0))
    if t == "text":
        size = float(it.get("size", 14))
        bold = bool(it.get("bold"))
        fn = add_font(pg, bold)
        lines = str(it.get("text", "")).split("\n")
        for k, line in enumerate(lines):
            pt = fitz.Point(it["x"], it["y"] + size * 0.9 + k * size * 1.25) * dm
            pg.insert_text(pt, line, fontsize=size, fontname=fn, color=color,
                           fill_opacity=opacity, rotate=pg.rotation)
    elif t in ("image", "signature"):
        src = job.extra.get(it.get("image_id")) or job.extra.get("image")
        if not src:
            raise ToolError("Görsel bulunamadı.")
        rr = r * dm
        rr.normalize()
        pg.insert_image(rr, filename=str(src), keep_proportion=True,
                        rotate=(-pg.rotation) % 360)
    elif t in ("rect", "whiteout"):
        rr = r * dm
        rr.normalize()
        if t == "whiteout":
            pg.draw_rect(rr, color=None, fill=(1, 1, 1), overlay=True)
        else:
            pg.draw_rect(rr, color=color, fill=fill, width=width, fill_opacity=opacity,
                         stroke_opacity=opacity)
    elif t == "ellipse":
        rr = r * dm
        rr.normalize()
        pg.draw_oval(rr, color=color, fill=fill, width=width, fill_opacity=opacity)
    elif t == "line":
        pg.draw_line(fitz.Point(it["x"], it["y"]) * dm,
                     fitz.Point(it["x2"], it["y2"]) * dm, color=color, width=width,
                     stroke_opacity=opacity)
    elif t == "ink":
        pts = [fitz.Point(x, y) * dm for x, y in it.get("points", [])]
        if len(pts) > 1:
            sh = pg.new_shape()
            sh.draw_polyline(pts)
            sh.finish(color=color, width=width, closePath=False, lineCap=1, lineJoin=1,
                      stroke_opacity=opacity)
            sh.commit()
    elif t == "highlight":
        rr = r * dm
        rr.normalize()
        pg.draw_rect(rr, color=None, fill=hex_to_rgb(it.get("color"), (1, 0.92, 0.23)),
                     fill_opacity=0.4)
    elif t == "field":   # form oluştur: metin alanı / onay kutusu
        _add_widget(pg, r, it)


def _add_widget(pg, r, it):
    w = fitz.Widget()
    kind = it.get("field_type", "text")
    w.field_type = {"text": fitz.PDF_WIDGET_TYPE_TEXT, "checkbox": fitz.PDF_WIDGET_TYPE_CHECKBOX,
                    "combobox": fitz.PDF_WIDGET_TYPE_COMBOBOX}.get(kind, fitz.PDF_WIDGET_TYPE_TEXT)
    w.field_name = it.get("name") or f"alan_{pg.number+1}_{int(r.x0)}_{int(r.y0)}"
    rr = r * pg.derotation_matrix
    rr.normalize()
    w.rect = rr
    w.text_fontsize = 0
    w.border_color = (0.4, 0.4, 0.9)
    w.fill_color = (0.93, 0.95, 1)
    if kind == "combobox":
        w.choice_values = [c.strip() for c in str(it.get("choices", "")).split(",") if c.strip()] or ["Seçenek"]
    pg.add_widget(w)


def forms(job: Job) -> Result:
    (f,) = job.need(1, 1, PDF)
    doc = open_pdf(f)
    mode = job.opt("mode", "fill")
    note = None
    if mode == "detect":
        n = detect_form_fields(doc)
        note = f"{n} form alanı otomatik oluşturuldu." if n else "Otomatik alan bulunamadı; alanları elle ekleyin."
    for it in job.opts.get("items") or []:     # elle eklenen alanlar
        it = dict(it, type="field")
        _add_widget(doc[int(it.get("page", 0))], fitz.Rect(it["x"], it["y"], it["x"] + it["w"], it["y"] + it["h"]), it)
    values = job.opts.get("values") or {}
    filled = 0
    for pg in doc:
        for w in pg.widgets() or []:
            if w.field_name in values:
                v = values[w.field_name]
                if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    w.field_value = w.on_state() if v in (True, "true", "on", "1", "Yes") else "Off"
                else:
                    w.field_value = str(v)
                w.update()
                filled += 1
    if job.flag("flatten"):
        flatten_forms(doc)
    if mode == "fill":
        note = f"{filled} alan dolduruldu." + (" Form düzleştirildi (artık düzenlenemez)." if job.flag("flatten") else "")
    return Result([save(doc, job.path(f"{stem(f)}_form.pdf"))], note=note)


def flatten_forms(doc):
    """Alan değerlerini Türkçe destekli fontla sayfaya yazar, alanları kaldırır."""
    for pg in doc:
        ws = list(pg.widgets() or [])
        items = [(w.rect, w.field_type, w.field_value, w.on_state() if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX else None,
                  w.text_fontsize) for w in ws]
        for w in ws:
            pg.delete_widget(w)
        for r, t, v, on, fs in items:
            vr = r * pg.rotation_matrix
            if t == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                if v and v != "Off":   # tik işareti çiz
                    w_, h_ = r.width, r.height
                    pg.draw_polyline([fitz.Point(r.x0 + w_ * .2, r.y0 + h_ * .55), fitz.Point(r.x0 + w_ * .42, r.y0 + h_ * .8),
                                      fitz.Point(r.x0 + w_ * .82, r.y0 + h_ * .22)], color=(0, 0, 0), width=max(1, h_ / 8))
                continue
            if v in (None, ""):
                continue
            size = fs or min(11, max(6, r.height * 0.7))
            fn = add_font(pg)
            pg.insert_text(fitz.Point(r.x0 + 2, r.y0 + (r.height + size * 0.7) / 2), str(v),
                           fontsize=size, fontname=fn)


def detect_form_fields(doc) -> int:
    """'______' boşlukları, ince yatay çizgiler ve '[ ]' / '☐' kutuları alana çevirir."""
    count = 0
    for pg in doc:
        existing = [w.rect for w in pg.widgets() or []]
        cands = []
        for x0, y0, x1, y1, word, *_ in pg.get_text("words"):
            if re.fullmatch(r"_{4,}|\.{6,}", word):
                cands.append(("text", fitz.Rect(x0, y0 - 6, x1, y1)))
            elif word in ("☐", "□", "[", "[]", "[ ]"):
                s = y1 - y0
                cands.append(("checkbox", fitz.Rect(x0, y0, x0 + s, y1)))
        for d in pg.get_drawings():
            for item in d["items"]:
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) < 1 and abs(p2.x - p1.x) > 60:
                        x0, x1 = sorted((p1.x, p2.x))
                        cands.append(("text", fitz.Rect(x0, p1.y - 14, x1, p1.y)))
            r = d.get("rect")
            if r and 6 < r.width < 16 and abs(r.width - r.height) < 2 and d.get("type") in ("s", "fs"):
                cands.append(("checkbox", fitz.Rect(r)))
        for kind, r in cands:
            vr = r * pg.rotation_matrix if pg.rotation else r
            if any(abs(vr.x0 - e.x0) < 3 and abs(vr.y0 - e.y0) < 3 for e in existing):
                continue
            existing.append(vr)
            # _add_widget görünür koordinat bekler
            _add_widget(pg, vr, {"field_type": kind})
            count += 1
    return count


def form_fields(path: Path) -> list[dict]:
    doc = open_pdf(path)
    out = []
    for pg in doc:
        for w in pg.widgets() or []:
            out.append({"name": w.field_name, "type": w.field_type_string, "value": w.field_value,
                        "page": pg.number, "choices": w.choice_values or [],
                        "on": w.on_state() if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX else None})
    return out


# =========================================================== GÜVENLİK
def unlock(job: Job) -> Result:
    import pikepdf
    files = job.need(1, exts=PDF)
    pw = job.opt("password", "")
    outs = []
    for f in files:
        try:
            with pikepdf.open(f, password=pw) as pdf:
                p = job.path(f"{stem(f)}_kilitsiz.pdf")
                pdf.save(p)   # şifreleme kaldırılır
                outs.append(p)
        except pikepdf.PasswordError:
            raise ToolError(f"{f.name}: parola yanlış. Açma parolasını girin.")
    return Result(zip_if_many(job, outs, "kilitsiz.zip"))


def protect(job: Job) -> Result:
    import pikepdf
    files = job.need(1, exts=PDF)
    user = job.opt("password", "")
    if len(user) < 1:
        raise ToolError("Bir parola girin.")
    if user != job.opt("password2", user):
        raise ToolError("Parolalar eşleşmiyor.")
    owner = job.opt("owner_password", "") or user + "_sahip"
    perms = pikepdf.Permissions(
        print_lowres=job.flag("allow_print", True), print_highres=job.flag("allow_print", True),
        extract=job.flag("allow_copy", False), modify_other=job.flag("allow_modify", False),
        modify_annotation=job.flag("allow_modify", False), modify_form=job.flag("allow_modify", False),
        modify_assembly=job.flag("allow_modify", False), accessibility=True)
    outs = []
    for f in files:
        with pikepdf.open(f) as pdf:
            p = job.path(f"{stem(f)}_korumali.pdf")
            pdf.save(p, encryption=pikepdf.Encryption(owner=owner, user=user, R=6, allow=perms))
            outs.append(p)
    return Result(zip_if_many(job, outs, "korumali.zip"), note="AES-256 ile şifrelendi.")


def sign(job: Job) -> Result:
    """İmza görseli (çizilen / yazılan / yüklenen) seçilen konumlara basılır."""
    (f,) = job.need(1, 1, PDF)
    doc = open_pdf(f)
    items = job.opts.get("items") or []
    if not items:
        raise ToolError("İmzayı sayfada yerleştirmek için önizlemeye tıklayın.")
    for it in items:
        pages = [int(it.get("page", 0))]
        if it.get("all_pages"):
            pages = list(range(doc.page_count))
        for p in pages:
            _draw_item(doc[p], it, job)
    return Result([save(doc, job.path(f"{stem(f)}_imzali.pdf"))],
                  note="Görsel imza eklendi. (Nitelikli e-imza/sertifika imzası için e-İmza aracınızı kullanın.)")


REDACT_PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "phone": r"(?:\+90[\s-]?)?\(?0?5\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}",
    "tckn": r"\b[1-9]\d{10}\b",
    "iban": r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b",
    "card": r"\b(?:\d{4}[\s-]?){3}\d{4}\b",
    "date": r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
}


def redact(job: Job) -> Result:
    (f,) = job.need(1, 1, PDF)
    doc = open_pdf(f)
    terms = [t.strip() for t in re.split(r"[\n,;]+", job.opt("terms", "")) if t.strip()]
    pats = [REDACT_PATTERNS[k] for k in REDACT_PATTERNS if job.flag(f"p_{k}")]
    fill = hex_to_rgb(job.opt("color", "#000000"))
    areas = job.opts.get("items") or []
    count = 0
    for pg in doc:
        rects = []
        for t in terms:
            rects += pg.search_for(t)
        if pats:
            text_page = pg.get_textpage()
            full = pg.get_text("text", textpage=text_page)
            for pat in pats:
                for m in re.finditer(pat, full):
                    rects += pg.search_for(m.group(0), textpage=text_page)
        for a in areas:
            if int(a.get("page", -1)) == pg.number:
                rects.append(fitz.Rect(a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]) * pg.derotation_matrix)
        for r in rects:
            pg.add_redact_annot(r, fill=fill)
            count += 1
        if rects:
            pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    if job.flag("metadata", True):
        doc.set_metadata({})
        doc.del_xml_metadata()
    if not count:
        raise ToolError("Karartılacak bir şey bulunamadı. Arama ifadelerini ya da alanları kontrol edin.")
    p = job.path(f"{stem(f)}_karartilmis.pdf")
    doc.save(p, garbage=4, deflate=True, clean=True)
    return Result([p], note=f"{count} alan kalıcı olarak silindi (metin altta da yok).")


def compare(job: Job) -> Result:
    a_path, b_path = job.need(2, 2, PDF)
    A, B = open_pdf(a_path), open_pdf(b_path)

    def words(doc):
        out = []
        for pg in doc:
            for w in pg.get_text("words", sort=True):
                out.append((pg.number, fitz.Rect(w[:4]), w[4]))
        return out

    wa, wb = words(A), words(B)
    pages_a, pages_b = list(A), list(B)   # sayfa nesneleri canlı kalmalı

    def mark(pages, ws, color):
        for pno, r, _ in ws:
            an = pages[pno].add_highlight_annot(r)
            an.set_colors(stroke=color)
            an.update()

    sm = difflib.SequenceMatcher(None, [w[2] for w in wa], [w[2] for w in wb], autojunk=False)
    added = removed = 0
    rows = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            seg = " ".join(w[2] for w in wa[i1:i2])
            rows.append(f'<span>{html.escape(_shorten(seg))} </span>')
            continue
        if i2 > i1:
            mark(pages_a, wa[i1:i2], (1, 0.45, 0.45))
            removed += i2 - i1
            rows.append('<del title="Sadece 1. belgede">' + html.escape(" ".join(w[2] for w in wa[i1:i2])) + '</del> ')
        if j2 > j1:
            mark(pages_b, wb[j1:j2], (0.45, 0.9, 0.45))
            added += j2 - j1
            rows.append('<ins title="Sadece 2. belgede">' + html.escape(" ".join(w[2] for w in wb[j1:j2])) + '</ins> ')
    pa = save(A, job.path(f"{stem(a_path)}_fark.pdf"))
    pb = save(B, job.path(f"{stem(b_path)}_fark.pdf"))
    ratio = sm.ratio() * 100
    summary = (f"Benzerlik: %{ratio:.1f} · 1. belgede olup 2.'de olmayan: {removed} kelime · "
               f"2.'de eklenen: {added} kelime · Sayfa: {A.page_count} / {B.page_count}")
    report = f"""<!doctype html><meta charset="utf-8"><title>PDF karşılaştırma</title>
<style>body{{font:15px/1.6 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#222}}
del{{background:#ffd6d6;color:#900}} ins{{background:#d4f7d4;color:#064;text-decoration:none}}
.s{{background:#f4f4f6;padding:10px 14px;border-radius:8px}}</style>
<h2>Karşılaştırma: {html.escape(a_path.name)} ↔ {html.escape(b_path.name)}</h2>
<p class="s">{summary}<br><del>kırmızı</del> = sadece 1. belgede, <ins>yeşil</ins> = sadece 2. belgede</p>
<div>{''.join(rows)}</div>"""
    rp = job.path("karsilastirma_raporu.html")
    rp.write_text(report, encoding="utf-8")
    return Result([rp, pa, pb], html=report, note=summary)


def _shorten(s: str, keep=18) -> str:
    w = s.split()
    if len(w) <= keep * 2:
        return s
    return " ".join(w[:keep]) + " … " + " ".join(w[-keep:])


def decode_data_url(s: str) -> bytes:
    if "," in s:
        s = s.split(",", 1)[1]
    return base64.b64decode(s)
