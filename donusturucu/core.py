"""Ortak yardımcılar: dosya deposu, sayfa aralığı ayrıştırma, font, dış araç tespiti."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "Dönüştürücü"
SYSTEM = platform.system()  # 'Windows' | 'Darwin' | 'Linux'


class ToolError(Exception):
    """Kullanıcıya gösterilecek, anlaşılır hata."""


# ---------------------------------------------------------------- ayarlar
def config_dir() -> Path:
    if SYSTEM == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif SYSTEM == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "Donusturucu"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_settings() -> dict:
    p = config_dir() / "ayarlar.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    p = config_dir() / "ayarlar.json"
    cur = load_settings()
    cur.update(data)
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- dosya deposu
@dataclass
class StoredFile:
    id: str
    name: str
    path: Path
    size: int
    created: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "size": self.size,
                "ext": self.path.suffix.lower().lstrip(".")}


class FileStore:
    """Yüklenen ve üretilen dosyalar geçici klasörde, kimlikle tutulur.
    Böylece bir aracın çıktısı başka araca girdi olarak verilebilir (iş akışı)."""

    def __init__(self, root: Path | None = None, max_age_hours: float = 12):
        self.root = Path(root or tempfile.mkdtemp(prefix="donusturucu_"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.files: dict[str, StoredFile] = {}
        self.lock = threading.Lock()
        self.max_age = max_age_hours * 3600

    def add_bytes(self, name: str, data: bytes) -> StoredFile:
        fid = uuid.uuid4().hex[:16]
        d = self.root / fid
        d.mkdir()
        p = d / safe_name(name)
        p.write_bytes(data)
        return self._register(fid, p)

    def add_path(self, src: Path, name: str | None = None) -> StoredFile:
        fid = uuid.uuid4().hex[:16]
        d = self.root / fid
        d.mkdir()
        p = d / safe_name(name or src.name)
        shutil.copy2(src, p)
        return self._register(fid, p)

    def _register(self, fid: str, p: Path) -> StoredFile:
        sf = StoredFile(fid, p.name, p, p.stat().st_size)
        with self.lock:
            self.files[fid] = sf
        return sf

    def get(self, fid: str) -> StoredFile:
        sf = self.files.get(fid)
        if not sf or not sf.path.exists():
            raise ToolError("Dosya bulunamadı ya da süresi doldu; lütfen yeniden yükleyin.")
        return sf

    def new_workdir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="is_", dir=self.root))

    def cleanup(self) -> None:
        now = time.time()
        with self.lock:
            old = [k for k, v in self.files.items() if now - v.created > self.max_age]
            for k in old:
                shutil.rmtree(self.files[k].path.parent, ignore_errors=True)
                del self.files[k]


_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_name(name: str) -> str:
    name = _BAD.sub("_", Path(name).name).strip(" .") or "dosya"
    return name[:150]


def stem(p: Path | str) -> str:
    return Path(p).stem


# ---------------------------------------------------------------- iş bağlamı
@dataclass
class Job:
    inputs: list[Path]
    opts: dict
    out: Path
    store: FileStore | None = None
    extra: dict = field(default_factory=dict)   # ör. imza görselleri {id: Path}

    def opt(self, key, default=None):
        v = self.opts.get(key, default)
        return default if v in (None, "") else v

    def flag(self, key, default=False) -> bool:
        v = self.opts.get(key, default)
        if isinstance(v, str):
            return v.lower() in ("1", "true", "on", "evet", "yes")
        return bool(v)

    def num(self, key, default=0.0) -> float:
        try:
            return float(str(self.opts.get(key, default)).replace(",", "."))
        except (TypeError, ValueError):
            return float(default)

    def path(self, name: str) -> Path:
        p = self.out / safe_name(name)
        i = 2
        while p.exists():
            p = self.out / f"{Path(name).stem} ({i}){Path(name).suffix}"
            i += 1
        return p

    def need(self, n_min=1, n_max=None, exts=None) -> list[Path]:
        files = self.inputs
        if exts:
            exts = {e.lower() for e in exts}
            bad = [f.name for f in files if f.suffix.lower().lstrip(".") not in exts]
            if bad:
                raise ToolError(f"Bu araç şu türleri kabul eder: {', '.join(sorted(exts))}. "
                                f"Uygun olmayan: {', '.join(bad)}")
        if len(files) < n_min:
            raise ToolError(f"En az {n_min} dosya seçin.")
        if n_max and len(files) > n_max:
            raise ToolError(f"En fazla {n_max} dosya seçebilirsiniz.")
        return files


@dataclass
class Result:
    files: list[Path] = field(default_factory=list)
    text: str | None = None       # kullanıcıya gösterilecek metin (özet vb.)
    html: str | None = None       # karşılaştırma raporu vb.
    note: str | None = None       # uyarı/bilgi


def zip_if_many(job: Job, files: list[Path], zipname: str, limit: int = 1) -> list[Path]:
    """Çok sayıda çıktı varsa tek ZIP de ekler (tek tek indirilebilir de)."""
    if len(files) <= limit:
        return files
    zp = job.path(zipname)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)
    return [zp] + files


# ---------------------------------------------------------------- sayfa aralıkları
def parse_pages(spec: str | None, total: int, default_all=True) -> list[int]:
    """'1,3-5,8-' gibi ifadeyi 0 tabanlı sayfa listesine çevirir. 'son' / 'last' desteklenir."""
    if not spec or not str(spec).strip():
        return list(range(total)) if default_all else []
    out: list[int] = []
    for part in re.split(r"[,;\s]+", str(spec).strip().lower()):
        if not part:
            continue
        part = part.replace("son", str(total)).replace("last", str(total))
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1) or 1)
            b = int(m.group(2) or total)
            if a > b:
                a, b = b, a
            rng = range(a, b + 1)
        elif part.isdigit():
            rng = [int(part)]
        else:
            raise ToolError(f"Sayfa ifadesi anlaşılamadı: '{part}'. Örnek: 1,3-5,8-")
        for n in rng:
            if 1 <= n <= total and (n - 1) not in out:
                out.append(n - 1)
    if not out:
        raise ToolError(f"Belirtilen sayfalar belgede yok (belge {total} sayfa).")
    return out


def parse_ranges(spec: str, total: int) -> list[list[int]]:
    """'1-3, 4-6, 7' → [[0,1,2],[3,4,5],[6]] (her aralık ayrı belge)."""
    groups = []
    for part in re.split(r"[,;]+", spec or ""):
        part = part.strip()
        if part:
            groups.append(parse_pages(part, total))
    if not groups:
        raise ToolError("En az bir sayfa aralığı girin. Örnek: 1-3, 4-6")
    return groups


def hex_to_rgb(h: str | None, default=(0, 0, 0)) -> tuple[float, float, float]:
    if not h:
        return default
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore
    except ValueError:
        return default


# ---------------------------------------------------------------- fontlar (Türkçe karakter)
_FONT_CACHE: dict[str, bytes] = {}


def unicode_font(bold=False) -> bytes:
    """Türkçe karakterleri (ş, ğ, ı, İ) basabilen font verisi."""
    key = "b" if bold else "r"
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    import pymupdf as fitz
    data = None
    try:
        data = fitz.Font("notosbo" if bold else "notos").buffer   # pymupdf-fonts
    except Exception:
        cands = []
        if SYSTEM == "Windows":
            w = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
            cands = [w / ("arialbd.ttf" if bold else "arial.ttf"), w / "segoeui.ttf"]
        elif SYSTEM == "Darwin":
            cands = [Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
                          else "/System/Library/Fonts/Supplemental/Arial.ttf")]
        else:
            cands = [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
                          else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
        for c in cands:
            if c.exists():
                data = c.read_bytes()
                break
    if data is None:
        data = fitz.Font("helv").buffer
    _FONT_CACHE[key] = data
    return data


def add_font(page, bold=False) -> str:
    name = "trB" if bold else "trR"
    page.insert_font(fontname=name, fontbuffer=unicode_font(bold))
    return name


def text_width(text: str, size: float, bold=False) -> float:
    import pymupdf as fitz
    return fitz.Font(fontbuffer=unicode_font(bold)).text_length(text, fontsize=size)


# ---------------------------------------------------------------- dış programlar
def _first_existing(paths) -> str | None:
    for p in paths:
        if p and Path(p).exists():
            return str(p)
    return None


def find_soffice() -> str | None:
    w = shutil.which("soffice") or shutil.which("libreoffice")
    if w:
        return w
    if SYSTEM == "Windows":
        pf = [os.environ.get("ProgramFiles", r"C:\Program Files"),
              os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
        return _first_existing([Path(p) / "LibreOffice" / "program" / "soffice.exe" for p in pf])
    if SYSTEM == "Darwin":
        return _first_existing(["/Applications/LibreOffice.app/Contents/MacOS/soffice"])
    return None


def find_browser() -> str | None:
    """HTML→PDF ve uygulama penceresi için Chromium tabanlı tarayıcı (Edge/Chrome)."""
    env = os.environ.get("DONUSTURUCU_BROWSER")
    if env and Path(env).exists():
        return env
    if SYSTEM == "Windows":
        pf = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
              os.environ.get("ProgramFiles", r"C:\Program Files"),
              os.environ.get("LOCALAPPDATA", "")]
        c = []
        for p in pf:
            c += [Path(p) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                  Path(p) / "Google" / "Chrome" / "Application" / "chrome.exe"]
        return _first_existing(c)
    if SYSTEM == "Darwin":
        return _first_existing([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"])
    for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        w = shutil.which(n)
        if w:
            return w
    return None


def find_ghostscript() -> str | None:
    for n in ("gs", "gswin64c", "gswin32c"):
        w = shutil.which(n)
        if w:
            return w
    if SYSTEM == "Windows":
        base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "gs"
        if base.exists():
            hits = sorted(base.glob("*/bin/gswin64c.exe"), reverse=True)
            if hits:
                return str(hits[0])
    return None


def find_ffmpeg() -> str | None:
    w = shutil.which("ffmpeg")
    if w:
        return w
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def has_ms_office() -> bool:
    if SYSTEM != "Windows":
        return False
    try:
        import winreg  # noqa
        for prog in ("Word.Application", "Excel.Application", "PowerPoint.Application"):
            try:
                winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog).Close()
                return True
            except OSError:
                pass
    except Exception:
        pass
    return False


TESSDATA_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{lang}.traineddata"


def tessdata_dir(langs: list[str], download=True) -> str:
    """OCR motoru PyMuPDF'in içinde. Sadece dil dosyaları gerekiyor; ilk kullanımda iner."""
    d = config_dir() / "tessdata"
    d.mkdir(exist_ok=True)
    for lang in langs:
        f = d / f"{lang}.traineddata"
        if f.exists() and f.stat().st_size > 100_000:
            continue
        if not download:
            raise ToolError(f"OCR dil dosyası yok: {lang}")
        import requests
        try:
            r = requests.get(TESSDATA_URL.format(lang=lang), timeout=120)
            r.raise_for_status()
            if len(r.content) < 100_000:
                raise ValueError("eksik dosya")
            f.write_bytes(r.content)
        except Exception as e:
            raise ToolError(f"OCR dil dosyası ({lang}) indirilemedi: {e}. İnternet bağlantısını "
                            f"kontrol edin ya da '{lang}.traineddata' dosyasını şu klasöre koyun: {d}")
    return str(d)


def run(cmd: list[str], timeout=600, cwd=None) -> subprocess.CompletedProcess:
    kw = {}
    if SYSTEM == "Windows":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW: siyah pencere açılmasın
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd, **kw)
    except subprocess.TimeoutExpired:
        raise ToolError("İşlem zaman aşımına uğradı.")


def capabilities() -> dict:
    """Ayarlar ekranında gösterilen bileşen durumu."""
    s = load_settings()
    tess = config_dir() / "tessdata"
    return {
        "isletim_sistemi": f"{SYSTEM} {platform.release()}",
        "ffmpeg": bool(find_ffmpeg()),
        "libreoffice": bool(find_soffice()),
        "ms_office": has_ms_office(),
        "tarayici": bool(find_browser()),
        "ghostscript": bool(find_ghostscript()),
        "ocr_dilleri": sorted(p.stem for p in tess.glob("*.traineddata")) if tess.exists() else [],
        "claude_anahtari": bool(s.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")),
        "ayar_klasoru": str(config_dir()),
    }
