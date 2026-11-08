"""PDF zekâsı: özetleme, çeviri, Markdown. Claude API anahtarı varsa Claude kullanılır;
yoksa özet için çevrimdışı yöntem, çeviri için ücretsiz Google Çeviri (deep-translator)."""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import pymupdf as fitz

from .core import Job, Result, ToolError, load_settings, stem, unicode_font, zip_if_many
from .pdf_tools import PDF, is_scanned, ocr_document, open_pdf, save

MODEL = "claude-opus-5-5"
LANGS = {"tr": "Türkçe", "en": "İngilizce", "de": "Almanca", "fr": "Fransızca", "es": "İspanyolca",
         "it": "İtalyanca", "ru": "Rusça", "ar": "Arapça", "zh-CN": "Çince", "ja": "Japonca",
         "nl": "Felemenkçe", "pt": "Portekizce", "pl": "Lehçe", "uk": "Ukraynaca", "fa": "Farsça",
         "ko": "Korece", "el": "Yunanca", "bg": "Bulgarca", "ro": "Rumence", "az": "Azerbaycanca"}


# ---------------------------------------------------------------- Claude
def api_key() -> str | None:
    return load_settings().get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")


def claude(prompt: str, system: str, max_tokens=16000, schema: dict | None = None) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key(), max_retries=3)
    kw = {}
    if schema:
        kw["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    try:
        with client.beta.messages.stream(
            model=MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw,
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise ToolError("Claude API anahtarı geçersiz. Ayarlar'dan kontrol edin.")
    except anthropic.RateLimitError:
        raise ToolError("Claude API kullanım sınırına ulaşıldı; biraz sonra tekrar deneyin.")
    except anthropic.APIConnectionError:
        raise ToolError("Claude API'ye bağlanılamadı (internet bağlantısını kontrol edin).")
    except anthropic.APIStatusError as e:
        raise ToolError(f"Claude API hatası ({e.status_code}): {e.message}")
    if msg.stop_reason == "refusal":
        raise ToolError("Model bu içeriği işlemeyi reddetti.")
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    if msg.stop_reason == "max_tokens":
        text += "\n[…çıktı uzunluk sınırında kesildi]"
    return text.strip()


# ---------------------------------------------------------------- metin çıkarma
def extract_text(job: Job) -> tuple[str, str]:
    pasted = (job.opt("text") or "").strip()
    if pasted:
        return pasted, "metin"
    files = job.need(1, exts=PDF + ["docx", "txt", "md"])
    parts = []
    for f in files:
        ext = f.suffix.lower()
        if ext == ".pdf":
            doc = open_pdf(f)
            if is_scanned(doc):
                doc = ocr_document(f)
            parts.append("\n".join(pg.get_text("text", sort=True) for pg in doc))
        elif ext == ".docx":
            import docx
            parts.append("\n".join(p.text for p in docx.Document(f).paragraphs))
        else:
            parts.append(f.read_text(encoding="utf-8", errors="replace"))
    text = "\n\n".join(parts).strip()
    if len(text) < 20:
        raise ToolError("Belgede okunabilir metin bulunamadı.")
    return text, stem(files[0])


# ---------------------------------------------------------------- ÖZET
LENGTH = {"short": ("kısa (3-5 cümle)", 0.08), "medium": ("orta (1-2 paragraf + ana maddeler)", 0.15),
          "long": ("ayrıntılı (bölüm bölüm)", 0.3)}


def summarize(job: Job) -> Result:
    text, name = extract_text(job)
    length = job.opt("length", "medium")
    lang = job.opt("lang", "tr")
    style = job.opt("style", "mixed")
    desc, ratio = LENGTH.get(length, LENGTH["medium"])
    note = None
    if api_key() and job.opt("engine", "auto") != "offline":
        style_txt = {"bullets": "madde işaretleri halinde", "paragraph": "akıcı paragraflar halinde",
                     "mixed": "kısa bir giriş paragrafı ve ardından ana noktalar madde halinde"}[style]
        summary = claude(
            f"Aşağıdaki belgeyi {LANGS.get(lang, 'Türkçe')} dilinde, {desc}, {style_txt} özetle. "
            f"Belgede olmayan bilgi ekleme; rakam ve isimleri aynen koru.\n\n<belge>\n{text}\n</belge>",
            system="Belgeleri doğru ve tarafsız özetleyen bir asistansın. Yalnızca özeti yaz.")
        note = "Claude ile özetlendi."
    else:
        summary = extractive_summary(text, ratio, bullets=style != "paragraph")
        note = ("Çevrimdışı özet (belgedeki en önemli cümleler seçildi). Daha iyi, yorumlu özet ve "
                "farklı dilde çıktı için Ayarlar'dan Claude API anahtarı ekleyin.")
    out_txt = job.path(f"{name}_ozet.txt")
    out_txt.write_text(summary, encoding="utf-8")
    out_docx = job.path(f"{name}_ozet.docx")
    _to_docx(summary, out_docx, f"{name} — Özet")
    return Result([out_docx, out_txt], text=summary, note=note)


_STOP = set("""ve ile de da ki bu şu o bir için gibi daha çok en ama fakat ancak veya ya hem ise mi mı mu mü
olan olarak olduğu ya da her ne kadar sonra önce kadar göre diye değil var yok çünkü yani ayrıca bunun
şunun onun bunu şunu onu biz siz onlar ben sen bizim sizin the a an and or of to in on for is are was
were be been with as by at from that this these those it its not but if than then so such""".split())


def _sentences(text: str) -> list[str]:
    text = re.sub(r"-\n(\w)", r"\1", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    sents = re.split(r"(?<=[.!?…])\s+(?=[A-ZÇĞİÖŞÜ0-9\"“(])", text)
    seen, out = set(), []
    for s in sents:
        s = s.strip()
        if 25 <= len(s) <= 600 and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def extractive_summary(text: str, ratio=0.15, bullets=True, max_sent=25) -> str:
    sents = _sentences(text)
    if not sents:
        return text[:1500]
    tok = lambda s: [w for w in re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", s.lower()) if w not in _STOP and len(w) > 2]
    freq = Counter(w for s in sents for w in tok(s))
    if not freq:
        return " ".join(sents[:5])
    top = max(freq.values())
    n = max(3, min(max_sent, math.ceil(len(sents) * ratio)))
    scores = []
    for i, s in enumerate(sents):
        ws = tok(s)
        sc = sum(freq[w] / top for w in ws) / (len(ws) ** 0.6 + 1)
        if i < 3:
            sc *= 1.25   # giriş cümleleri genelde önemli
        if re.search(r"\d", s):
            sc *= 1.1
        scores.append((sc, i))
    chosen = sorted(i for _, i in sorted(scores, reverse=True)[:n])
    picked = [sents[i] for i in chosen]
    return "\n".join(f"• {s}" for s in picked) if bullets else " ".join(picked)


def _to_docx(text: str, path: Path, title: str):
    import docx
    d = docx.Document()
    d.add_heading(title, level=1)
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue
        m = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)", line)
        if m:
            d.add_paragraph(m.group(1).replace("**", ""), style="List Bullet")
        elif line.startswith("#"):
            d.add_heading(line.lstrip("# "), level=2)
        else:
            d.add_paragraph(line.replace("**", ""))
    d.save(path)


# ---------------------------------------------------------------- ÇEVİRİ (düzen korunur)
TR_SCHEMA = {"type": "object", "properties": {"t": {"type": "array", "items": {"type": "string"}}},
             "required": ["t"], "additionalProperties": False}


def _translate_batch(texts: list[str], target: str, use_claude: bool) -> list[str]:
    if not texts:
        return []
    if use_claude:
        out = claude(
            f"Aşağıdaki JSON dizisindeki her metni {LANGS.get(target, target)} diline çevir. "
            f"Sırayı ve eleman sayısını ({len(texts)}) aynen koru; sayıları, kodları, e-postaları "
            f"ve özel isimleri değiştirme. Sonucu {{\"t\": [...]}} olarak ver.\n\n"
            + json.dumps(texts, ensure_ascii=False),
            system="Profesyonel belge çevirmenisin.", schema=TR_SCHEMA)
        try:
            res = json.loads(out)["t"]
        except Exception:
            m = re.search(r"\[.*\]", out, re.S)
            res = json.loads(m.group(0)) if m else []
        if len(res) == len(texts):
            return [str(x) for x in res]
        # sayı tutmazsa tek tek
        return [_translate_batch([t], target, True)[0] for t in texts]
    from deep_translator import GoogleTranslator
    tr = GoogleTranslator(source="auto", target=target)
    res = []
    for t in texts:
        try:
            res.append(tr.translate(t) or t)
        except Exception:
            res.append(t)
    return res


def translate(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    target = job.opt("lang", "tr")
    use_claude = bool(api_key()) and job.opt("engine", "auto") != "google"
    if not use_claude:
        try:
            import deep_translator  # noqa
        except ImportError:
            raise ToolError("Çeviri için Ayarlar'dan Claude API anahtarı ekleyin "
                            "ya da 'deep-translator' paketini kurun.")
    arch = fitz.Archive()
    arch.add(unicode_font(), "tr.ttf")
    arch.add(unicode_font(True), "trb.ttf")
    outs = []
    for f in files:
        doc = open_pdf(f)
        if is_scanned(doc):
            doc = ocr_document(f)
        for pg in doc:
            blocks = [b for b in pg.get_text("dict")["blocks"] if b.get("type") == 0]
            items = []
            for b in blocks:
                txt = " ".join("".join(s["text"] for s in ln["spans"]) for ln in b["lines"]).strip()
                if len(re.sub(r"[\W\d_]", "", txt)) < 2:
                    continue
                sp = b["lines"][0]["spans"][0]
                items.append((fitz.Rect(b["bbox"]), txt, sp["size"], sp["color"], bool(sp["flags"] & 16)))
            if not items:
                continue
            translated = []
            for i in range(0, len(items), 40):
                translated += _translate_batch([t for _, t, *_ in items[i:i + 40]], target, use_claude)
            for r, *_ in items:
                pg.add_redact_annot(r)
            pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
            for (r, _, size, color, bold), t in zip(items, translated):
                c = f"#{color:06x}"
                css = ("@font-face{font-family:tr;src:url(tr.ttf)}"
                       "@font-face{font-family:tr;src:url(trb.ttf);font-weight:bold}"
                       f"*{{font-family:tr;font-size:{size:.1f}pt;color:{c};line-height:1.15;"
                       f"font-weight:{'bold' if bold else 'normal'}}}")
                import html as h
                pg.insert_htmlbox(r + (0, 0, 2, 2), h.escape(t), css=css, archive=arch,
                                  rotate=pg.rotation)
        outs.append(save(doc, job.path(f"{stem(f)}_{target}.pdf")))
    note = "Claude ile çevrildi." if use_claude else (
        "Google Çeviri (ücretsiz) ile çevrildi — metin Google'a gönderildi. Daha kaliteli çeviri için "
        "Ayarlar'dan Claude API anahtarı ekleyin.")
    return Result(zip_if_many(job, outs, "ceviri.zip"), note=note)


# ---------------------------------------------------------------- MARKDOWN
def pdf_to_markdown(job: Job) -> Result:
    files = job.need(1, exts=PDF)
    import pymupdf4llm
    outs, preview = [], []
    for f in files:
        doc = open_pdf(f)
        if is_scanned(doc):
            doc = ocr_document(f)
        md = pymupdf4llm.to_markdown(doc, show_progress=False)
        p = job.path(f"{stem(f)}.md")
        p.write_text(md, encoding="utf-8")
        outs.append(p)
        preview.append(md)
    text = "\n\n---\n\n".join(preview)
    return Result(zip_if_many(job, outs, "markdown.zip"), text=text[:20000])
