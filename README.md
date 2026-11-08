# Dönüştürücü

Bilgisayarınızda çalışan PDF ve video dönüştürücü. Dosyalar internete yüklenmez, her şey yerelde işlenir. Tek istisna Özet ve Çeviri araçları: Claude API anahtarı girerseniz metin Claude'a, girmezseniz çeviri metni Google Çeviri'ye gider.

## Kurulum (bir kez)

| Sistem | Yapılacak |
|---|---|
| **Windows** | `Kurulum_Windows.bat` dosyasına çift tıklayın. |
| **macOS** | `Kurulum_Mac.command` dosyasına sağ tıklayın → **Aç**. İlk açılışta macOS "tanımlanamayan geliştirici" uyarısı verebilir. |

Kurulum şunları yapar:
1. Python 3.10 veya üstü yoksa kurar: Windows'ta winget ile, macOS'ta Homebrew ile.
2. Uygulamayı şu klasöre kopyalar:
   - Windows: `%LOCALAPPDATA%\Donusturucu`
   - macOS: `~/Library/Application Support/Donusturucu`
3. Paketleri kurar. İlk kurulum 2-5 dakika sürer.
4. **Masaüstüne "Dönüştürücü" kısayolu** koyar. Windows'ta Başlat menüsüne de ekler.

Sonra masaüstündeki simgeye çift tıklamanız yeterli. Uygulama kendi penceresinde açılır. Pencereyi kapatınca arka plandaki sunucu 2 dakika içinde kendiliğinden kapanır.

**Kaldırmak için** yukarıdaki klasörü ve masaüstündeki kısayolu silin.

## Araçlar (34)

- **Video ve ses:** Videoyu sese dönüştürür (MP3, M4A, WAV, FLAC, OGG, OPUS, AAC). Kırpma, mono, normalize ve bit hızı ayarları var.
- **PDF düzenle:** Birleştir, ayır (aralık, her N sayfa, tek tek ya da boyuta göre), sayfa kaldır, sayfa ayıkla, sırala/döndür/boş sayfa ekle, PDF'e tara (kamera ve otomatik kırpma).
- **Optimize:** Küçült (3 düzey), onar, OCR (Türkçe dahil, dil dosyası ilk kullanımda iner).
- **PDF'e:** JPG/PNG, Word, PowerPoint, Excel, HTML (web adresi ya da dosya).
- **PDF'den:** JPG/PNG (sayfa ya da gömülü görsel), Word, PowerPoint (düzenlenebilir metin), Excel (tablolar), PDF/A, Markdown.
- **Düzenleme:** Metin, görsel, şekil, vurgu, beyaz örtü ve kalem ekleme. Döndürme, sayfa numarası, filigran (metin ya da görsel), kırpma, form işleri (algıla, oluştur, doldur, düzleştir).
- **Güvenlik:** Kilit açma, AES-256 ile parola koyma, imza (çiz, yaz ya da yükle), kalıcı karartma (TC, IBAN, e-posta, telefon kalıpları ya da elle seçim), iki PDF'i karşılaştırma.
- **Zekâ:** Özetleyici ve düzeni koruyan çeviri. Claude anahtarı varsa Claude kullanılır, yoksa özet çevrimdışı, çeviri Google ile yapılır.

Her işlemin sonunda **"Sonucu başka bir araçla işle"** düğmeleri çıkar. Böylece araçları zincirleyebilirsiniz, örneğin önce birleştir, sonra küçült, sonra parola koy.

## İsteğe bağlı bileşenler

| Bileşen | Neden |
|---|---|
| Microsoft Office (Windows) veya [LibreOffice](https://www.libreoffice.org/download/) | Word, Excel ve PowerPoint dosyalarını PDF'e çevirmek için gerekir. Windows'ta Office varsa ayrıca bir şey kurmanız gerekmez. |
| [Ghostscript](https://ghostscript.com/releases/gsdnld.html) | Resmî PDF/A uyumu için. Kurulu değilse temel PDF/A işaretlemesi yapılır. |
| Claude API anahtarı | Daha iyi özet ve çeviri için. Ayarlar (⚙) → Claude API anahtarı. |

## Geliştirici

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python run.py           # pencereyle
.venv/bin/python -m pytest -q tests
```
