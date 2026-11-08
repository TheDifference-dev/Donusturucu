"""Her aracı örnek dosyalarla çalıştırır ve çıktıyı içerik düzeyinde doğrular.
Çalıştırma:  python -m pytest -q tests   (converter klasöründen)"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pymupdf as fitz
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from donusturucu import core  # noqa: E402
from donusturucu.core import Job, ToolError  # noqa: E402
from donusturucu.registry import BY_ID  # noqa: E402

TR = "Şirket bütçesi İstanbul çığır öğün ılık"


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("ornek")
    # 6 sayfalık metinli PDF + tablo
    doc = fitz.open()
    for i in range(6):
        pg = doc.new_page()
        fn = core.add_font(pg)
        pg.insert_text((72, 80), f"Sayfa {i+1} başlık", fontsize=20, fontname=fn)
        pg.insert_text((72, 120), f"{TR}. Bu belge test içindir. Toplam tutar 1.250,50 TL.",
                       fontsize=11, fontname=fn)
        pg.insert_text((72, 140), "İletişim: deneme@ornek.com  TC: 12345678901", fontsize=11, fontname=fn)
        if i == 0:   # 3x3 tablo
            for r in range(4):
                pg.draw_line((72, 200 + r * 20), (372, 200 + r * 20))
            for c in range(4):
                pg.draw_line((72 + c * 100, 200), (72 + c * 100, 260))
            for r, row in enumerate([["Ürün", "Adet", "Fiyat"], ["Kalem", "10", "25"], ["Defter", "3", "40"]]):
                for c, val in enumerate(row):
                    pg.insert_text((78 + c * 100, 214 + r * 20), val, fontsize=10, fontname=fn)
            pg.insert_text((72, 320), "Ad Soyad: ______________", fontsize=11, fontname=fn)
        # gömülü görsel
        im = Image.new("RGB", (800, 600), (30, 120, 200))
        ImageDraw.Draw(im).ellipse((100, 100, 700, 500), fill=(250, 200, 0))
        b = io.BytesIO(); im.save(b, "PNG")
        pg.insert_image(fitz.Rect(72, 400, 372, 625), stream=b.getvalue())
    pdf = d / "ornek.pdf"
    doc.save(pdf)
    doc2 = fitz.open(pdf)
    pg = doc2[1]
    fn = core.add_font(pg)
    pg.insert_text((72, 170), "Yeni eklenen cümle burada.", fontsize=11, fontname=fn)
    pdf2 = d / "ornek_v2.pdf"
    doc2.save(pdf2)
    # taranmış (yalnızca görsel) PDF
    scan = fitz.open()
    pix = fitz.open(pdf)[0].get_pixmap(dpi=150)
    p = scan.new_page(width=595, height=842)
    p.insert_image(p.rect, pixmap=pix)
    scanned = d / "taranmis.pdf"
    scan.save(scanned)
    # görsel
    img = d / "foto.jpg"
    im = Image.new("RGB", (1200, 900), (90, 90, 90))
    ImageDraw.Draw(im).rectangle((200, 150, 1000, 750), fill=(245, 245, 240))
    ImageDraw.Draw(im).text((300, 300), "Belge metni", fill=(0, 0, 0))
    im.save(img, quality=90)
    png = d / "logo.png"
    Image.new("RGBA", (300, 120), (200, 0, 0, 255)).save(png)
    # docx / xlsx / pptx
    import docx, openpyxl
    from pptx import Presentation
    dd = docx.Document(); dd.add_heading("Word başlığı", 1); dd.add_paragraph(TR); dd.save(d / "belge.docx")
    wb = openpyxl.Workbook(); wb.active.append(["Ad", "Tutar"]); wb.active.append(["Çağrı", 12]); wb.save(d / "tablo.xlsx")
    pr = Presentation(); s = pr.slides.add_slide(pr.slide_layouts[1]); s.shapes.title.text = "Sunum"; pr.save(d / "sunum.pptx")
    (d / "sayfa.html").write_text(f"<html><body><h1>Merhaba</h1><p>{TR}</p></body></html>", encoding="utf-8")
    # 3 saniyelik video (görüntü + ses)
    ff = core.find_ffmpeg()
    vid = d / "klip.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(vid)], check=True)
    mute = d / "sessiz.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mute)], check=True)
    return d


def run_tool(tid, inputs, tmp_path, **opts):
    out = tmp_path / tid
    out.mkdir(exist_ok=True)
    job = Job(inputs=[Path(p) for p in inputs], opts=opts, out=out,
              extra={k: v for k, v in opts.pop("_extra", {}).items()} if "_extra" in opts else {})
    return BY_ID[tid]["fn"](job)


def pages(p):
    return fitz.open(p).page_count


def text(p):
    return "".join(pg.get_text() for pg in fitz.open(p))


# ---------------------------------------------------------------- testler
def test_video_to_audio_formats(samples, tmp_path):
    for fmt in ["mp3", "wav", "m4a", "flac", "ogg", "opus"]:
        r = run_tool("video_to_audio", [samples / "klip.mp4"], tmp_path, format=fmt, bitrate="128k")
        out = r.files[0]
        assert out.suffix == f".{fmt}" and out.stat().st_size > 1000
        probe = subprocess.run([core.find_ffmpeg(), "-i", str(out)], capture_output=True).stderr.decode()
        assert "Audio:" in probe and "Video:" not in probe, probe
        assert "00:00:03" in probe or "00:00:02.9" in probe


def test_video_trim_and_mute(samples, tmp_path):
    r = run_tool("video_to_audio", [samples / "klip.mp4"], tmp_path, format="mp3", start="1", end="2")
    probe = subprocess.run([core.find_ffmpeg(), "-i", str(r.files[0])], capture_output=True).stderr.decode()
    assert "Duration: 00:00:01" in probe or "Duration: 00:00:00.9" in probe, probe
    with pytest.raises(ToolError):
        run_tool("video_to_audio", [samples / "sessiz.mp4"], tmp_path, format="mp3")


def test_merge_split_remove_extract(samples, tmp_path):
    m = run_tool("merge", [samples / "ornek.pdf", samples / "ornek_v2.pdf", samples / "foto.jpg"], tmp_path).files[0]
    assert pages(m) == 13 and len(fitz.open(m).get_toc()) == 3
    s = run_tool("split", [samples / "ornek.pdf"], tmp_path, mode="ranges", ranges="1-2, 3-5, 6").files
    assert s[0].suffix == ".zip" and [pages(x) for x in s[1:]] == [2, 3, 1]
    s = run_tool("split", [samples / "ornek.pdf"], tmp_path, mode="every", every=4).files
    assert [pages(x) for x in s[1:]] == [4, 2]
    s = run_tool("split", [samples / "ornek.pdf"], tmp_path, mode="size", max_mb=0.05).files
    assert sum(pages(x) for x in s if x.suffix == ".pdf") == 6
    r = run_tool("remove_pages", [samples / "ornek.pdf"], tmp_path, pages="2, 4-5").files[0]
    assert pages(r) == 3 and "Sayfa 3 başlık" in text(r) and "Sayfa 2 başlık" not in text(r)
    e = run_tool("extract_pages", [samples / "ornek.pdf"], tmp_path, pages="6,1").files[0]
    assert pages(e) == 2 and fitz.open(e)[0].get_text().startswith("Sayfa 1")


def test_organize(samples, tmp_path):
    layout = [{"f": 1, "p": 1, "r": 90}, {"blank": True}, {"f": 0, "p": 0, "r": 0}]
    r = run_tool("organize", [samples / "ornek.pdf", samples / "ornek_v2.pdf"], tmp_path, layout=layout).files[0]
    d = fitz.open(r)
    assert d.page_count == 3 and d[0].rotation == 90 and "Yeni eklenen" in d[0].get_text()
    assert d[1].get_text().strip() == "" and "Sayfa 1" in d[2].get_text()


def test_scan_and_jpg(samples, tmp_path):
    r = run_tool("scan_to_pdf", [samples / "foto.jpg"], tmp_path, filter="bw").files[0]
    assert pages(r) == 1
    r = run_tool("jpg_to_pdf", [samples / "foto.jpg", samples / "logo.png"], tmp_path, size="a4", margin="small").files[0]
    d = fitz.open(r)
    assert d.page_count == 2 and d[0].rect.width > d[0].rect.height   # yatay görsel → yatay sayfa


def test_compress_repair(samples, tmp_path):
    big = tmp_path / "buyuk.pdf"
    doc = fitz.open()
    for _ in range(3):
        pg = doc.new_page()
        im = Image.effect_noise((2400, 2400), 60).convert("RGB")
        b = io.BytesIO(); im.save(b, "PNG")
        pg.insert_image(pg.rect, stream=b.getvalue())
    doc.save(big)
    r = run_tool("compress", [big], tmp_path, level="recommended")
    assert r.files[0].stat().st_size < big.stat().st_size * 0.6, r.note
    broken = tmp_path / "bozuk.pdf"
    data = (samples / "ornek.pdf").read_bytes()
    broken.write_bytes(data[: len(data) - 400])   # xref tablosu kesik
    r = run_tool("repair", [broken], tmp_path)
    assert pages(r.files[0]) >= 1


def test_ocr(samples, tmp_path):
    r = run_tool("ocr", [samples / "taranmis.pdf"], tmp_path, lang="tur+eng")
    t = text(r.files[0])
    assert "Sayfa" in t and "başlık" in t, t[:200]
    assert abs(fitz.open(r.files[0])[0].rect.width - 595) < 2


def test_office_and_html_to_pdf(samples, tmp_path):
    for tid, f in [("word_to_pdf", "belge.docx"), ("excel_to_pdf", "tablo.xlsx"), ("ppt_to_pdf", "sunum.pptx")]:
        if not core.find_soffice() and not core.has_ms_office():
            pytest.skip("Ofis dönüştürücüsü yok")
        r = run_tool(tid, [samples / f], tmp_path).files[0]
        assert r.suffix == ".pdf" and pages(r) >= 1
    assert "Word başlığı" in text(tmp_path / "word_to_pdf" / "belge.pdf")
    r = run_tool("html_to_pdf", [samples / "sayfa.html"], tmp_path).files[0]
    assert "Merhaba" in text(r) and "İstanbul" in text(r)


def test_pdf_to_formats(samples, tmp_path):
    r = run_tool("pdf_to_jpg", [samples / "ornek.pdf"], tmp_path, mode="pages", dpi="72", pages="1-2").files
    assert r[0].suffix == ".zip" and len(r) == 3 and Image.open(r[1]).size[0] == 595
    r = run_tool("pdf_to_jpg", [samples / "ornek.pdf"], tmp_path, mode="extract").files
    assert Image.open(r[0]).size == (800, 600)
    w = run_tool("pdf_to_word", [samples / "ornek.pdf"], tmp_path).files[0]
    import docx
    body = "\n".join(p.text for p in docx.Document(w).paragraphs)
    assert "Sayfa 1 başlık" in body and "İstanbul" in body
    p = run_tool("pdf_to_ppt", [samples / "ornek.pdf"], tmp_path).files[0]
    from pptx import Presentation
    prs = Presentation(p)
    alltext = " ".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
    assert len(prs.slides) == 6 and "Sayfa 3" in alltext
    x = run_tool("pdf_to_excel", [samples / "ornek.pdf"], tmp_path).files[0]
    import openpyxl
    ws = openpyxl.load_workbook(x).worksheets[0]
    vals = [[c.value for c in row] for row in ws.iter_rows()]
    assert ["Ürün", "Adet", "Fiyat"] in vals and ["Kalem", 10, 25] in vals, vals
    a = run_tool("pdf_to_pdfa", [samples / "ornek.pdf"], tmp_path).files[0]
    import pikepdf
    with pikepdf.open(a) as pdf:
        assert "/OutputIntents" in pdf.Root or core.find_ghostscript()
    m = run_tool("pdf_to_markdown", [samples / "ornek.pdf"], tmp_path)
    assert "Sayfa 1" in m.text and m.files[0].suffix == ".md"


def test_edit_tools(samples, tmp_path):
    items = [{"type": "text", "page": 0, "x": 300, "y": 300, "text": "Düzenleme ŞĞİ", "size": 16, "color": "#ff0000"},
             {"type": "rect", "page": 0, "x": 50, "y": 50, "w": 100, "h": 40, "color": "#0000ff"},
             {"type": "ink", "page": 1, "points": [[10, 10], [50, 60], [90, 20]], "color": "#00aa00"},
             {"type": "whiteout", "page": 2, "x": 70, "y": 60, "w": 200, "h": 30},
             {"type": "image", "page": 3, "x": 100, "y": 650, "w": 150, "h": 60, "image_id": "logo"}]
    r = run_tool("edit", [samples / "ornek.pdf"], tmp_path, items=items, _extra={"logo": samples / "logo.png"}).files[0]
    d = fitz.open(r)
    assert "Düzenleme ŞĞİ" in d[0].get_text() and len(d[3].get_images()) == 2
    r = run_tool("rotate", [samples / "ornek.pdf"], tmp_path, angle="90", which="odd").files[0]
    assert [p.rotation for p in fitz.open(r)][:2] == [90, 0]
    r = run_tool("page_numbers", [samples / "ornek.pdf"], tmp_path, format="Sayfa {n} / {total}", pages="2-", start=1).files[0]
    d = fitz.open(r)
    assert "Sayfa 1 / 5" in d[1].get_text() and "/ 5" not in d[0].get_text()
    r = run_tool("watermark", [samples / "ornek.pdf"], tmp_path, kind="text", text="GİZLİ", mosaic=True).files[0]
    assert "GİZLİ" in fitz.open(r)[0].get_text()
    r = run_tool("watermark", [samples / "ornek.pdf"], tmp_path, kind="image", _extra={"image": samples / "logo.png"}).files[0]
    assert len(fitz.open(r)[0].get_images()) == 2
    r = run_tool("crop", [samples / "ornek.pdf"], tmp_path, box={"x0": 50, "y0": 50, "x1": 400, "y1": 400}).files[0]
    assert abs(fitz.open(r)[0].rect.width - 350) < 1
    r = run_tool("crop", [samples / "ornek.pdf"], tmp_path, top=10, bottom=10, left=20, right=20).files[0]
    assert abs(fitz.open(r)[0].rect.width - (595 - 40 * 72 / 25.4)) < 1


def test_forms(samples, tmp_path):
    from donusturucu.pdf_tools import form_fields
    r = run_tool("forms", [samples / "ornek.pdf"], tmp_path, mode="detect").files[0]
    fields = form_fields(r)
    assert fields, "underscore alanı algılanmalı"
    name = fields[0]["name"]
    r2 = run_tool("forms", [r], tmp_path, mode="fill", values={name: "Çağla Öztürk"}).files[0]
    assert form_fields(r2)[0]["value"] == "Çağla Öztürk"
    r3 = run_tool("forms", [r2], tmp_path, mode="fill", flatten=True).files[0]
    assert not form_fields(r3) and "Çağla Öztürk" in text(r3)


def test_security(samples, tmp_path):
    p = run_tool("protect", [samples / "ornek.pdf"], tmp_path, password="1234", password2="1234").files[0]
    assert fitz.open(p).needs_pass
    with pytest.raises(ToolError):
        run_tool("unlock", [p], tmp_path, password="yanlis")
    u = run_tool("unlock", [p], tmp_path, password="1234").files[0]
    assert not fitz.open(u).needs_pass and pages(u) == 6
    s = run_tool("sign", [samples / "ornek.pdf"], tmp_path, _extra={"sig": samples / "logo.png"},
                 items=[{"type": "signature", "page": 0, "x": 400, "y": 700, "w": 120, "h": 50, "image_id": "sig"}]).files[0]
    assert len(fitz.open(s)[0].get_images()) == 2
    r = run_tool("redact", [samples / "ornek.pdf"], tmp_path, terms="İstanbul", p_email=True, p_tckn=True).files[0]
    t = text(r)
    assert "İstanbul" not in t and "deneme@ornek.com" not in t and "12345678901" not in t and "Sayfa 1" in t
    c = run_tool("compare", [samples / "ornek.pdf", samples / "ornek_v2.pdf"], tmp_path)
    assert "eklenen: 4 kelime" in c.note and "Yeni eklenen" in c.html


def test_summarize_offline_and_markdown(samples, tmp_path, monkeypatch):
    monkeypatch.setattr("donusturucu.ai_tools.api_key", lambda: None)
    r = run_tool("summarize", [samples / "ornek.pdf"], tmp_path, length="short")
    assert r.text and "•" in r.text and r.files[0].suffix == ".docx"
    r = run_tool("summarize", [], tmp_path, text="Birinci cümle burada yer alıyor ve uzundur. " * 3 +
                 "Bütçe 2026 yılında yüzde on artacak ve yatırım planı onaylandı. Son cümle de buradadır ve kısa değildir.")
    assert "Bütçe" in r.text


def test_translate_with_mock(samples, tmp_path, monkeypatch):
    import donusturucu.ai_tools as ai
    monkeypatch.setattr(ai, "api_key", lambda: "test")
    monkeypatch.setattr(ai, "_translate_batch", lambda texts, target, use: [f"[EN] {t[:10]}" for t in texts])
    r = run_tool("translate", [samples / "ornek.pdf"], tmp_path, lang="en")
    t = text(r.files[0])
    assert "[EN]" in t and "İstanbul" not in t


def test_claude_request_shape(monkeypatch):
    """Claude çağrısının parametrelerini sahte istemciyle kontrol eder (ağ yok)."""
    import donusturucu.ai_tools as ai
    seen = {}

    class Msg:
        stop_reason = "end_turn"
        content = [type("B", (), {"type": "text", "text": '{"t": ["Hello"]}'})()]

    class Stream:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get_final_message(self): return Msg()

    class Client:
        def __init__(self, **kw):
            self.beta = type("X", (), {"messages": type("Y", (), {"stream": staticmethod(lambda **k: (seen.update(k), Stream())[1])})()})()

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", Client)
    monkeypatch.setattr(ai, "api_key", lambda: "k")
    assert ai._translate_batch(["Merhaba"], "en", True) == ["Hello"]
    assert seen["model"] == "claude-opus-5-5" and seen["fallbacks"] == "default"
    assert seen["output_config"]["format"]["type"] == "json_schema"
