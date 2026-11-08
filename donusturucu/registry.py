"""Araç kataloğu: arayüz bu tanımlardan formları otomatik üretir."""
from __future__ import annotations

from . import ai_tools as ai
from . import convert_tools as cv
from . import media_tools as md
from . import pdf_tools as pt

PDF, IMG = pt.PDF, pt.IMG

CATEGORIES = [
    ("media", "Video ve Ses", "#7c3aed"),
    ("organize", "PDF Düzenle", "#e5322d"),
    ("optimize", "PDF Optimize Et", "#16a34a"),
    ("to_pdf", "PDF'e Dönüştür", "#f59e0b"),
    ("from_pdf", "PDF'den Dönüştür", "#2563eb"),
    ("edit", "PDF Düzenleme", "#db2777"),
    ("security", "PDF Güvenliği", "#0f766e"),
    ("ai", "PDF Zekâsı", "#9333ea"),
]

POSITIONS = [["tl", "Sol üst"], ["tc", "Üst orta"], ["tr", "Sağ üst"], ["ml", "Sol orta"],
             ["mc", "Orta"], ["mr", "Sağ orta"], ["bl", "Sol alt"], ["bc", "Alt orta"], ["br", "Sağ alt"]]
LANG_OPTS = [[k, v] for k, v in ai.LANGS.items()]


def o(key, label, type="text", default=None, choices=None, show_if=None, help=None, **kw):
    d = {"key": key, "label": label, "type": type, "default": default}
    if choices:
        d["choices"] = choices
    if show_if:
        d["show_if"] = show_if
    if help:
        d["help"] = help
    d.update(kw)
    return d


TOOLS = [
    # ------------------------------------------------------------ VİDEO
    dict(id="video_to_audio", cat="media", icon="🎵", fn=md.video_to_audio,
         title="Videoyu Sese Dönüştür",
         desc="MP4, MOV, MKV, AVI, WEBM… videolardan sesi MP3, WAV, M4A, FLAC, OGG veya OPUS olarak çıkarın.",
         accept=md.VIDEO + md.AUDIO, multi=True,
         opts=[o("format", "Ses biçimi", "select", "mp3", [["mp3", "MP3"], ["m4a", "M4A (AAC)"], ["wav", "WAV (kayıpsız)"],
                                                          ["flac", "FLAC (kayıpsız)"], ["ogg", "OGG Vorbis"], ["opus", "OPUS"], ["aac", "AAC"]]),
               o("bitrate", "Kalite (bit hızı)", "select", "192k", [["96k", "96 kbps (küçük)"], ["128k", "128 kbps"], ["192k", "192 kbps (önerilen)"],
                                                                  ["256k", "256 kbps"], ["320k", "320 kbps (en yüksek)"]],
                 show_if={"format": ["mp3", "m4a", "ogg", "opus", "aac"]}),
               o("start", "Başlangıç (isteğe bağlı)", "text", "", placeholder="örn. 0:30"),
               o("end", "Bitiş (isteğe bağlı)", "text", "", placeholder="örn. 2:15"),
               o("samplerate", "Örnekleme hızı", "select", "auto", [["auto", "Kaynakla aynı"], ["44100", "44.1 kHz"], ["48000", "48 kHz"], ["22050", "22 kHz"]]),
               o("mono", "Mono'ya çevir", "checkbox", False),
               o("normalize", "Ses seviyesini dengele (normalize)", "checkbox", False)]),

    # ------------------------------------------------------------ DÜZENLE
    dict(id="merge", cat="organize", icon="⧉", fn=pt.merge, title="PDF Birleştir",
         desc="Birden fazla PDF'i (ve görseli) istediğiniz sırayla tek dosyada birleştirin. Sürükleyerek sıralayın.",
         accept=PDF + IMG, multi=True, sortable=True,
         opts=[o("bookmarks", "Her dosya için yer imi ekle", "checkbox", True)]),
    dict(id="split", cat="organize", icon="✂", fn=pt.split, title="PDF Ayır",
         desc="PDF'i aralıklara, her N sayfaya, tek tek sayfalara ya da dosya boyutuna göre bölün.",
         accept=PDF, multi=False, preview=True,
         opts=[o("mode", "Bölme şekli", "select", "ranges", [["ranges", "Özel aralıklar"], ["every", "Her N sayfada bir"],
                                                               ["all", "Her sayfa ayrı dosya"], ["size", "Dosya boyutuna göre"]]),
               o("ranges", "Aralıklar", "text", "1-2, 3-5", show_if={"mode": ["ranges"]}, help="Her aralık ayrı PDF olur. Örnek: 1-3, 4-6, 7-"),
               o("merge_ranges", "Aralıkları tek PDF'te birleştir", "checkbox", False, show_if={"mode": ["ranges"]}),
               o("every", "Kaç sayfada bir", "number", 1, show_if={"mode": ["every"]}, min=1),
               o("max_mb", "En fazla boyut (MB)", "number", 5, show_if={"mode": ["size"]}, min=0.1, step=0.1)]),
    dict(id="remove_pages", cat="organize", icon="🗑", fn=pt.remove_pages, title="Sayfaları Kaldır",
         desc="İstemediğiniz sayfaları PDF'ten silin.", accept=PDF, multi=False, preview=True, page_pick="pages",
         opts=[o("pages", "Silinecek sayfalar", "text", "", help="Önizlemeden tıklayın ya da yazın: 2, 5-7")]),
    dict(id="extract_pages", cat="organize", icon="📑", fn=pt.extract_pages, title="Sayfaları Ayıkla",
         desc="Seçtiğiniz sayfalardan yeni bir PDF oluşturun.", accept=PDF, multi=False, preview=True, page_pick="pages",
         opts=[o("pages", "Ayıklanacak sayfalar", "text", "", help="Önizlemeden tıklayın ya da yazın: 1, 3-4"),
               o("separate", "Her sayfayı ayrı dosya yap", "checkbox", False)]),
    dict(id="organize", cat="organize", icon="▦", fn=pt.organize, title="PDF Düzenle (Sırala)",
         desc="Sayfaları sürükleyip sıralayın, döndürün, silin, boş sayfa ekleyin; birden fazla PDF'i karıştırın.",
         accept=PDF, multi=True, ui="organize", opts=[]),
    dict(id="scan_to_pdf", cat="organize", icon="📷", fn=pt.scan_to_pdf, title="PDF'e Tara",
         desc="Kamerayla ya da telefon fotoğraflarından belgeyi kırpıp netleştirerek PDF yapın.",
         accept=IMG, multi=True, sortable=True, camera=True,
         opts=[o("filter", "Görünüm", "select", "auto", [["auto", "Otomatik (gri, net)"], ["bw", "Siyah-beyaz belge"],
                                                          ["gray", "Gri tonlama"], ["color", "Renkli"], ["none", "Orijinal"]]),
               o("auto_crop", "Kâğıdı otomatik algıla ve düzelt", "checkbox", True)]),

    # ------------------------------------------------------------ OPTİMİZE
    dict(id="compress", cat="optimize", icon="🗜", fn=pt.compress, title="PDF Küçültme",
         desc="Kaliteyi koruyarak PDF dosya boyutunu düşürün.", accept=PDF, multi=True,
         opts=[o("level", "Sıkıştırma düzeyi", "radio", "recommended",
                 [["low", "Az sıkıştırma — yüksek kalite"], ["recommended", "Önerilen — iyi kalite, iyi sıkıştırma"],
                  ["extreme", "Aşırı sıkıştırma — düşük kalite"]]),
               o("grayscale", "Görselleri gri tonlamaya çevir", "checkbox", False)]),
    dict(id="repair", cat="optimize", icon="🛠", fn=pt.repair, title="PDF'i Onar",
         desc="Bozuk ya da açılmayan PDF'leri onarıp kurtarılabilen veriyi geri alın.", accept=PDF, multi=True, opts=[]),
    dict(id="ocr", cat="optimize", icon="🔍", fn=pt.ocr, title="OCR PDF",
         desc="Taranmış PDF ve görselleri aranabilir, seçilebilir metne dönüştürün.", accept=PDF + IMG, multi=True,
         opts=[o("lang", "Belge dili", "select", "tur+eng", [["tur+eng", "Türkçe + İngilizce"], ["tur", "Türkçe"], ["eng", "İngilizce"],
                                                             ["deu", "Almanca"], ["fra", "Fransızca"], ["spa", "İspanyolca"],
                                                             ["ita", "İtalyanca"], ["rus", "Rusça"], ["ara", "Arapça"]],
                 help="Dil dosyası ilk kullanımda bir kez indirilir (~4 MB)."),
               o("dpi", "Tarama çözünürlüğü", "select", "300", [["200", "200 dpi (hızlı)"], ["300", "300 dpi (önerilen)"], ["400", "400 dpi (küçük yazı)"]]),
               o("skip_text", "Zaten metin içeren sayfaları atla", "checkbox", True)]),

    # ------------------------------------------------------------ PDF'E
    dict(id="jpg_to_pdf", cat="to_pdf", icon="🖼", fn=cv.jpg_to_pdf, title="JPG'den PDF'e",
         desc="JPG, PNG, WEBP, TIFF… görselleri yönlendirme ve kenar boşluğu ayarıyla PDF'e çevirin.",
         accept=IMG, multi=True, sortable=True,
         opts=[o("orientation", "Sayfa yönü", "select", "auto", [["auto", "Otomatik"], ["portrait", "Dikey"], ["landscape", "Yatay"]]),
               o("size", "Sayfa boyutu", "select", "a4", [["a4", "A4"], ["letter", "US Letter"], ["a3", "A3"], ["a5", "A5"], ["fit", "Görsel boyutu"]]),
               o("margin", "Kenar boşluğu", "select", "none", [["none", "Yok"], ["small", "Küçük"], ["big", "Büyük"]]),
               o("separate", "Her görsel ayrı PDF", "checkbox", False)]),
    dict(id="word_to_pdf", cat="to_pdf", icon="W", fn=cv.word_to_pdf, title="Word'den PDF'e",
         desc="DOC, DOCX, ODT, RTF ve TXT dosyalarını PDF'e dönüştürün.", accept=cv.WORD, multi=True, opts=[], needs="office"),
    dict(id="ppt_to_pdf", cat="to_pdf", icon="P", fn=cv.ppt_to_pdf, title="PowerPoint'ten PDF'e",
         desc="PPT ve PPTX sunumlarını PDF'e dönüştürün.", accept=cv.PPT, multi=True, opts=[], needs="office"),
    dict(id="excel_to_pdf", cat="to_pdf", icon="X", fn=cv.excel_to_pdf, title="Excel'den PDF'e",
         desc="XLS, XLSX, ODS ve CSV tablolarını PDF'e dönüştürün.", accept=cv.XLS, multi=True, opts=[], needs="office"),
    dict(id="html_to_pdf", cat="to_pdf", icon="🌐", fn=cv.html_to_pdf, title="HTML'den PDF'e",
         desc="Bir web sayfasının adresini girin ya da HTML dosyası seçin; PDF olarak kaydedin.",
         accept=["html", "htm"], multi=True, optional_files=True,
         opts=[o("url", "Web adresi", "text", "", placeholder="https://ornek.com"),
               o("header_footer", "Tarih/başlık üst-alt bilgisi ekle", "checkbox", False)]),

    # ------------------------------------------------------------ PDF'DEN
    dict(id="pdf_to_jpg", cat="from_pdf", icon="🖼", fn=cv.pdf_to_jpg, title="PDF'den JPG'ye",
         desc="Her sayfayı JPG/PNG olarak kaydedin ya da PDF içindeki görselleri ayıklayın.", accept=PDF, multi=True,
         opts=[o("mode", "Ne yapılsın?", "radio", "pages", [["pages", "Sayfaları görsele çevir"], ["extract", "İçindeki görselleri ayıkla"]]),
               o("format", "Biçim", "select", "jpg", [["jpg", "JPG"], ["png", "PNG"]]),
               o("dpi", "Çözünürlük", "select", "150", [["72", "72 dpi"], ["150", "150 dpi"], ["300", "300 dpi (baskı)"]], show_if={"mode": ["pages"]}),
               o("pages", "Sayfalar (boş = hepsi)", "text", "", show_if={"mode": ["pages"]})]),
    dict(id="pdf_to_word", cat="from_pdf", icon="W", fn=cv.pdf_to_word, title="PDF'den Word'e",
         desc="PDF'leri düzenlenebilir DOCX belgelerine dönüştürün (tablo, görsel ve düzen korunur).",
         accept=PDF, multi=True,
         opts=[o("ocr", "Taranmış belgelerde önce OCR uygula", "checkbox", True)]),
    dict(id="pdf_to_ppt", cat="from_pdf", icon="P", fn=cv.pdf_to_ppt, title="PDF'den PowerPoint'e",
         desc="Her sayfayı slayta çevirin; metinler düzenlenebilir kutular olarak gelir.", accept=PDF, multi=True,
         opts=[o("mode", "Slayt türü", "radio", "editable", [["editable", "Düzenlenebilir metin"], ["image", "Sadece görsel (birebir görünüm)"]])]),
    dict(id="pdf_to_excel", cat="from_pdf", icon="X", fn=cv.pdf_to_excel, title="PDF'den Excel'e",
         desc="PDF'teki tabloları Excel'e aktarın; sayılar sayı olarak gelir.", accept=PDF, multi=True,
         opts=[o("layout", "Yerleşim", "radio", "per_table", [["per_table", "Her tablo ayrı sayfada"], ["single", "Tüm tablolar tek sayfada"]]),
               o("ocr", "Taranmış belgelerde önce OCR uygula", "checkbox", True)]),
    dict(id="pdf_to_pdfa", cat="from_pdf", icon="A", fn=cv.pdf_to_pdfa, title="PDF'den PDF/A'ya",
         desc="Uzun süreli arşivleme için ISO standardı PDF/A'ya dönüştürün.", accept=PDF, multi=True,
         opts=[o("level", "Uyumluluk", "select", "2b", [["1b", "PDF/A-1b"], ["2b", "PDF/A-2b (önerilen)"], ["3b", "PDF/A-3b"]])]),
    dict(id="pdf_to_markdown", cat="from_pdf", icon="M↓", fn=ai.pdf_to_markdown, title="PDF'den Markdown'a",
         desc="Başlık, tablo, liste ve bağlantıları koruyarak Markdown'a dönüştürün.", accept=PDF, multi=True, opts=[]),

    # ------------------------------------------------------------ DÜZENLEME
    dict(id="edit", cat="edit", icon="✎", fn=pt.edit, title="PDF'i Düzenle",
         desc="Metin, görsel, şekil, vurgu, beyaz örtü ve serbest çizim ekleyin.", accept=PDF, multi=False,
         ui="placer", tools=["text", "image", "rect", "ellipse", "line", "highlight", "whiteout", "ink"], opts=[]),
    dict(id="rotate", cat="edit", icon="⟳", fn=pt.rotate, title="PDF'i Döndür",
         desc="Tüm sayfaları ya da seçtiklerinizi döndürün.", accept=PDF, multi=True,
         opts=[o("angle", "Açı", "radio", "90", [["90", "90° sağa"], ["180", "180°"], ["270", "90° sola"]]),
               o("which", "Sayfalar", "select", "all", [["all", "Tümü"], ["odd", "Tek sayfalar"], ["even", "Çift sayfalar"], ["custom", "Seçilenler"]]),
               o("pages", "Sayfa listesi", "text", "", show_if={"which": ["custom"]})]),
    dict(id="page_numbers", cat="edit", icon="#", fn=pt.page_numbers, title="Sayfa Numaraları",
         desc="Konum, boyut, biçim ve başlangıç numarasını seçerek sayfa numarası ekleyin.", accept=PDF, multi=True,
         opts=[o("position", "Konum", "position", "bc", POSITIONS),
               o("format", "Biçim", "select", "{n}", [["{n}", "1"], ["{n} / {total}", "1 / 10"], ["Sayfa {n}", "Sayfa 1"],
                                                      ["Sayfa {n} / {total}", "Sayfa 1 / 10"], ["- {n} -", "- 1 -"]]),
               o("start", "İlk numara", "number", 1),
               o("pages", "Numaralanacak sayfalar (boş = hepsi)", "text", "", help="Örn. kapağı atlamak için: 2-"),
               o("size", "Yazı boyutu", "number", 11, min=5, max=72),
               o("color", "Renk", "color", "#000000"),
               o("margin", "Kenara uzaklık (pt)", "number", 28),
               o("facing", "Karşılıklı sayfalar (sağ/sol aynalı)", "checkbox", False)]),
    dict(id="watermark", cat="edit", icon="💧", fn=pt.watermark, title="Filigran",
         desc="Metin ya da görsel filigranı; yazı tipi, saydamlık, açı ve konum seçerek ekleyin.", accept=PDF, multi=True,
         wm_image=True,
         opts=[o("kind", "Filigran türü", "radio", "text", [["text", "Metin"], ["image", "Görsel"]]),
               o("text", "Metin", "text", "GİZLİ", show_if={"kind": ["text"]}),
               o("size", "Yazı boyutu", "number", 60, show_if={"kind": ["text"]}),
               o("color", "Renk", "color", "#d32f2f", show_if={"kind": ["text"]}),
               o("bold", "Kalın", "checkbox", True, show_if={"kind": ["text"]}),
               o("scale", "Görsel genişliği (% sayfa)", "number", 40, show_if={"kind": ["image"]}),
               o("position", "Konum", "position", "mc", POSITIONS),
               o("mosaic", "Döşeme (tüm sayfaya tekrarla)", "checkbox", False),
               o("opacity", "Saydamlık (%)", "range", 30, min=5, max=100),
               o("angle", "Açı (derece)", "number", 45, show_if={"kind": ["text"]}),
               o("layer", "Katman", "select", "over", [["over", "İçeriğin üstünde"], ["under", "İçeriğin altında"]]),
               o("pages", "Sayfalar (boş = hepsi)", "text", "")]),
    dict(id="crop", cat="edit", icon="⌗", fn=pt.crop, title="PDF Kırpma",
         desc="Önizlemede alan seçerek ya da kenar boşluklarını girerek sayfaları kırpın.", accept=PDF, multi=False,
         ui="placer", tools=["crop"],
         opts=[o("which", "Uygulanacak sayfalar", "select", "all", [["all", "Tüm sayfalar"], ["custom", "Seçilen sayfalar"]]),
               o("pages", "Sayfa listesi", "text", "", show_if={"which": ["custom"]}),
               o("top", "Üst (mm)", "number", 10, help="Alan seçmezseniz kenar boşlukları kullanılır."),
               o("right", "Sağ (mm)", "number", 10), o("bottom", "Alt (mm)", "number", 10), o("left", "Sol (mm)", "number", 10)]),
    dict(id="forms", cat="edit", icon="☑", fn=pt.forms, title="PDF Formlar",
         desc="Form alanlarını otomatik algılayın, yeni alan ekleyin ya da mevcut formu doldurun.", accept=PDF, multi=False,
         ui="forms", tools=["field"],
         opts=[o("mode", "İşlem", "radio", "fill", [["fill", "Formu doldur"], ["detect", "Alanları otomatik algıla ve oluştur"],
                                                    ["create", "Alanları elle ekle"]]),
               o("flatten", "Formu düzleştir (değerleri sabitle)", "checkbox", False)]),

    # ------------------------------------------------------------ GÜVENLİK
    dict(id="unlock", cat="security", icon="🔓", fn=pt.unlock, title="PDF Kilidini Aç",
         desc="PDF parolasını ve kopyalama/yazdırma kısıtlamalarını kaldırın.", accept=PDF, multi=True,
         opts=[o("password", "Parola (kısıtlama sadece izinlerdeyse boş bırakın)", "password", "")]),
    dict(id="protect", cat="security", icon="🔒", fn=pt.protect, title="PDF'i Koru",
         desc="PDF'i AES-256 parolasıyla şifreleyin, yazdırma/kopyalama izinlerini belirleyin.", accept=PDF, multi=True,
         opts=[o("password", "Parola", "password", ""), o("password2", "Parola (tekrar)", "password", ""),
               o("allow_print", "Yazdırmaya izin ver", "checkbox", True),
               o("allow_copy", "Metin kopyalamaya izin ver", "checkbox", False),
               o("allow_modify", "Düzenlemeye izin ver", "checkbox", False),
               o("owner_password", "Sahip parolası (isteğe bağlı)", "password", "")]),
    dict(id="sign", cat="security", icon="✍", fn=pt.sign, title="PDF İmzala",
         desc="İmzanızı çizin, yazın ya da görsel yükleyin; sayfada istediğiniz yere yerleştirin.", accept=PDF, multi=False,
         ui="placer", tools=["signature", "text"], opts=[]),
    dict(id="redact", cat="security", icon="▇", fn=pt.redact, title="PDF'yi Karart (Redakte)",
         desc="Hassas metin ve alanları kalıcı olarak silin: arama, hazır kalıplar (TC, IBAN, e-posta) ya da elle seçim.",
         accept=PDF, multi=False, ui="placer", tools=["redact"],
         opts=[o("terms", "Karartılacak ifadeler (her satıra bir)", "textarea", ""),
               o("p_tckn", "TC kimlik numaraları", "checkbox", False), o("p_iban", "IBAN'lar", "checkbox", False),
               o("p_email", "E-posta adresleri", "checkbox", False), o("p_phone", "Telefon numaraları", "checkbox", False),
               o("p_card", "Kart numaraları", "checkbox", False), o("p_date", "Tarihler", "checkbox", False),
               o("color", "Örtü rengi", "color", "#000000"),
               o("metadata", "Belge bilgilerini (yazar vb.) de sil", "checkbox", True)]),
    dict(id="compare", cat="security", icon="⇄", fn=pt.compare, title="PDF Karşılaştırma",
         desc="İki sürümü karşılaştırın: eklenen ve silinen kelimeler renkli işaretlenir.", accept=PDF, multi=True,
         exact_files=2, opts=[]),

    # ------------------------------------------------------------ ZEKÂ
    dict(id="summarize", cat="ai", icon="✦", fn=ai.summarize, title="Yapay Zekâ Özetleyici",
         desc="PDF, Word ya da yapıştırdığınız metnin özetini çıkarın.", accept=PDF + ["docx", "txt", "md"], multi=True,
         optional_files=True,
         opts=[o("text", "…ya da metni buraya yapıştırın", "textarea", ""),
               o("length", "Uzunluk", "radio", "medium", [["short", "Kısa"], ["medium", "Orta"], ["long", "Ayrıntılı"]]),
               o("style", "Biçim", "select", "mixed", [["mixed", "Giriş + maddeler"], ["bullets", "Sadece maddeler"], ["paragraph", "Paragraf"]]),
               o("lang", "Özet dili", "select", "tr", LANG_OPTS, help="Dil seçimi Claude ile çalışır.")]),
    dict(id="translate", cat="ai", icon="文", fn=ai.translate, title="PDF Çevir",
         desc="PDF'i yazı tipi ve sayfa düzenini koruyarak başka dile çevirin.", accept=PDF, multi=True,
         opts=[o("lang", "Hedef dil", "select", "tr", LANG_OPTS),
               o("engine", "Çeviri motoru", "select", "auto", [["auto", "Otomatik (Claude varsa Claude)"], ["google", "Google Çeviri (ücretsiz)"]])]),
]

BY_ID = {t["id"]: t for t in TOOLS}


def public_catalog() -> dict:
    tools = [{k: v for k, v in t.items() if k != "fn"} for t in TOOLS]
    return {"categories": [{"id": c, "title": n, "color": col} for c, n, col in CATEGORIES], "tools": tools}
