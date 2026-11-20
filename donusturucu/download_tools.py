"""YouTube (ve yt-dlp'nin desteklediği diğer siteler) bağlantısından video / ses indirme.

- İndirme motoru: yt-dlp (Python paketi). YouTube sık değiştiği için uygulama, PyPI'daki
  yeni yt-dlp sürümünü kendi ayar klasörüne indirip onu kullanabilir (update_downloader).
- YouTube'un imza çözümü için JavaScript çalışma ortamı gerekir: deno (pakete gömülü).
- Birleştirme / ses dönüştürme: uygulamayla gelen ffmpeg."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path

from .core import Job, Result, ToolError, config_dir, find_ffmpeg, stem, zip_if_many

PACKAGES = ("yt-dlp", "yt-dlp-ejs")          # PyPI adları
UPDATE_DIR_NAME = "indirici"
_LOCK = threading.Lock()
_LOADED = {}

VIDEO_HEIGHTS = ["best", "2160", "1440", "1080", "720", "480", "360"]
AUDIO_CODECS = {"mp3": "mp3", "m4a": "m4a", "opus": "opus", "wav": "wav", "flac": "flac"}
BROWSERS = ["firefox", "edge", "chrome", "brave", "opera", "vivaldi", "chromium", "safari"]


# ---------------------------------------------------------------- yt-dlp yükleme / güncelleme
def _update_dir() -> Path:
    d = config_dir() / UPDATE_DIR_NAME
    d.mkdir(exist_ok=True)
    return d


def _activate_updates() -> None:
    """Ayar klasöründe daha yeni yt-dlp tekerleği (wheel) varsa onu içe aktarma yoluna öne koyar."""
    for wheel in sorted(_update_dir().glob("*.whl")):
        p = str(wheel)
        if p not in sys.path:
            sys.path.insert(0, p)


def load_ytdlp():
    with _LOCK:
        if "mod" not in _LOADED:
            _activate_updates()
            try:
                import yt_dlp  # noqa
            except ImportError:
                raise ToolError("İndirme bileşeni (yt-dlp) yüklü değil. 'pip install yt-dlp[default]' ile kurun.")
            _LOADED["mod"] = yt_dlp
        return _LOADED["mod"]


def ytdlp_version() -> str:
    try:
        return load_ytdlp().version.__version__
    except Exception:
        return "-"


def _ver_tuple(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def _installed_version(pkg: str) -> str:
    try:
        from importlib.metadata import version
        return version(pkg)
    except Exception:
        return "0"


def update_downloader(force=False, timeout=20) -> dict:
    """PyPI'dan yt-dlp ve yt-dlp-ejs'in son sürümünü ayar klasörüne indirir.
    Yeni sürüm, uygulama bir sonraki açılışta (ya da yt-dlp henüz yüklenmediyse hemen) kullanılır."""
    import requests
    stamp = _update_dir() / "son_kontrol.json"
    if not force:
        try:
            if time.time() - json.loads(stamp.read_text())["t"] < 24 * 3600:
                return {"durum": "yakın zamanda kontrol edildi", "surum": ytdlp_version()}
        except Exception:
            pass
    _activate_updates()
    result = {"durum": "güncel", "surum": _installed_version("yt-dlp")}
    for pkg in PACKAGES:
        info = requests.get(f"https://pypi.org/pypi/{pkg}/json", timeout=timeout).json()
        latest = info["info"]["version"]
        wheel = next((u for u in info["urls"] if u["packagetype"] == "bdist_wheel"
                      and u["filename"].endswith("py3-none-any.whl")), None)
        if not wheel:
            continue
        target = _update_dir() / wheel["filename"]
        if target.exists() or _ver_tuple(latest) <= _ver_tuple(_installed_version(pkg)):
            continue
        data = requests.get(wheel["url"], timeout=180).content
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(data)
        with zipfile.ZipFile(tmp) as z:   # bozuk inişi kullanma
            if z.testzip() is not None:
                tmp.unlink(missing_ok=True)
                raise ToolError("İndirilen güncelleme bozuk.")
        prefix = pkg.replace("-", "_") + "-"
        for old in _update_dir().glob(prefix + "*.whl"):
            old.unlink(missing_ok=True)
        tmp.replace(target)
        if pkg == "yt-dlp":
            result = {"durum": "güncellendi — uygulamayı kapatıp açın", "surum": latest}
    stamp.write_text(json.dumps({"t": time.time()}))
    return result


def auto_update_in_background():
    def run():
        try:
            update_downloader(force=False)
        except Exception as e:
            print("İndirici güncelleme kontrolü başarısız:", e)
    threading.Thread(target=run, daemon=True).start()


def find_js_runtime() -> str | None:
    """YouTube için deno. PyInstaller paketinde deno_bin/ altında gelir."""
    names = ["deno.exe", "deno"]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        for n in names:
            p = Path(base) / "deno_bin" / n
            if p.exists():
                return str(p)
    try:
        import deno
        p = deno.find_deno_bin()
        if p and Path(p).exists():
            return str(p)
    except Exception:
        pass
    return shutil.which("deno")


# ---------------------------------------------------------------- indirme
def _urls(job: Job) -> list[str]:
    raw = job.opt("url", "") or ""
    urls = [u.strip() for u in re.split(r"[\s,]+", raw) if u.strip()]
    if not urls:
        raise ToolError("Bir video bağlantısı yapıştırın. Örnek: https://www.youtube.com/watch?v=…")
    bad = [u for u in urls if not re.match(r"^https?://", u)]
    if bad:
        raise ToolError(f"Geçersiz bağlantı: {bad[0]}")
    if len(urls) > 50:
        raise ToolError("Tek seferde en fazla 50 bağlantı.")
    return urls


def build_options(job: Job, outdir: Path, hook=None) -> dict:
    kind = job.opt("kind", "video")
    ff = find_ffmpeg()
    opts = {
        "outtmpl": str(outdir / "%(title).120B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "restrictfilenames": False,
        "noplaylist": not job.flag("playlist"),
        "playlistend": int(job.num("max_items", 25)) if job.flag("playlist") else None,
        "ignoreerrors": "only_download" if job.flag("playlist") else False,
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "overwrites": True,
        "progress_hooks": [hook] if hook else [],
        "postprocessor_hooks": [],
        "postprocessors": [],
    }
    if ff:
        opts["ffmpeg_location"] = ff
    js = find_js_runtime()
    if js:
        opts["js_runtimes"] = {"deno": {"path": js}}
    browser = job.opt("cookies", "none")
    if browser and browser != "none":
        if browser not in BROWSERS:
            raise ToolError("Bilinmeyen tarayıcı.")
        opts["cookiesfrombrowser"] = (browser,)

    if kind == "audio":
        codec = job.opt("audio_format", "mp3")
        if codec not in AUDIO_CODECS:
            raise ToolError("Desteklenmeyen ses biçimi.")
        opts["format"] = "bestaudio/best"
        pp = {"key": "FFmpegExtractAudio", "preferredcodec": AUDIO_CODECS[codec]}
        if codec in ("mp3", "m4a", "opus"):
            pp["preferredquality"] = str(job.opt("bitrate", "192")).rstrip("k")
        opts["postprocessors"].append(pp)
        if job.flag("metadata", True):
            opts["postprocessors"].append({"key": "FFmpegMetadata", "add_metadata": True})
            if codec in ("mp3", "m4a", "flac", "opus"):
                opts["writethumbnail"] = True
                opts["postprocessors"].append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    else:
        h = job.opt("quality", "1080")
        if h not in VIDEO_HEIGHTS:
            raise ToolError("Geçersiz kalite.")
        cap = "" if h == "best" else f"[height<={h}]"
        if job.opt("container", "mp4") == "mp4":
            # Windows'ta her oynatıcıda açılsın diye H.264 + AAC tercih edilir
            opts["format"] = (f"bv*{cap}[vcodec^=avc1]+ba[acodec^=mp4a]/bv*{cap}[ext=mp4]+ba[ext=m4a]/"
                              f"bv*{cap}+ba/b{cap}/b")
            opts["merge_output_format"] = "mp4"
            opts["postprocessors"].append({"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"})
        else:
            opts["format"] = f"bv*{cap}+ba/b{cap}/b"
            opts["merge_output_format"] = "mkv"
        if job.flag("subtitles"):
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = ["tr", "en", "tr.*", "en.*"]
            opts["postprocessors"].append({"key": "FFmpegEmbedSubtitle"})
        if job.flag("metadata", True):
            opts["postprocessors"].append({"key": "FFmpegMetadata", "add_metadata": True})
    if not ff:
        raise ToolError("ffmpeg bulunamadı; indirme sonrası birleştirme yapılamaz.")
    return opts


def _friendly(err: str) -> str:
    e = err
    if "Sign in to confirm" in e or "not a bot" in e:
        return ("YouTube robot doğrulaması istedi. Seçeneklerden 'Tarayıcı çerezlerini kullan' ile YouTube'a "
                "giriş yaptığınız tarayıcıyı seçip tekrar deneyin (Firefox en sorunsuz çalışanıdır).")
    if "Private video" in e or "private" in e.lower() and "video" in e.lower():
        return "Bu video gizli; yalnızca sahibi ve izin verdiği kişiler görebilir."
    if "age" in e.lower() and ("confirm" in e.lower() or "restricted" in e.lower()):
        return "Yaş sınırlı video: 'Tarayıcı çerezlerini kullan' ile oturum açık tarayıcıyı seçin."
    if "Video unavailable" in e or "not available" in e:
        return "Video kullanılamıyor (kaldırılmış ya da bölgenizde engelli olabilir)."
    if "Unsupported URL" in e:
        return "Bu bağlantı desteklenmiyor. Video sayfasının adresini yapıştırın."
    if "could not find" in e.lower() and "cookies" in e.lower():
        return "Seçilen tarayıcının çerezleri bulunamadı. Tarayıcı kurulu ve YouTube'a giriş yapılmış olmalı."
    if "Could not copy" in e and "cookie" in e.lower():
        return "Tarayıcı açıkken çerezleri okunamadı. Tarayıcıyı kapatıp tekrar deneyin ya da Firefox'u seçin."
    if "Requested format is not available" in e:
        return ("İstenen kalite bulunamadı. Kaliteyi 'En iyi' yapın ya da Ayarlar'dan indiriciyi güncelleyin.")
    return e.replace("ERROR: ", "")[:500] + "\n\nSorun sürerse Ayarlar → 'İndiriciyi güncelle'yi deneyin."


def media_download(job: Job) -> Result:
    urls = _urls(job)
    yt_dlp = load_ytdlp()
    workdir = job.out / "_indir"
    workdir.mkdir(exist_ok=True)
    state = {"i": 0, "n": len(urls)}

    def hook(d):
        st = d.get("status")
        name = Path(d.get("filename") or "").name
        if st == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            frac = (got / tot) if tot else None
            speed = d.get("speed") or 0
            eta = d.get("eta")
            txt = f"İndiriliyor: {name[:60]}"
            if tot:
                txt += f" — {got/1048576:.1f} / {tot/1048576:.1f} MB"
            if speed:
                txt += f" · {speed/1048576:.1f} MB/sn"
            if eta:
                txt += f" · {int(eta)//60}:{int(eta)%60:02d} kaldı"
            job.progress(frac, txt)
        elif st == "finished":
            job.progress(None, f"İşleniyor (birleştirme/dönüştürme): {name[:60]}")

    opts = build_options(job, workdir, hook)
    errors, titles = [], []
    with yt_dlp.YoutubeDL(opts) as ydl:
        for i, url in enumerate(urls, 1):
            state["i"] = i
            job.progress(0, f"Bağlantı {i}/{len(urls)} hazırlanıyor…")
            try:
                info = ydl.extract_info(url, download=True)
                if info:
                    entries = info.get("entries") or [info]
                    titles += [e.get("title", "") for e in entries if e]
            except yt_dlp.utils.DownloadError as e:
                errors.append(f"{url}\n  → {_friendly(str(e))}")
            except Exception as e:
                errors.append(f"{url}\n  → {type(e).__name__}: {e}")
    keep = {".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".opus", ".wav", ".flac", ".ogg", ".aac", ".mov"}
    outs = []
    for f in sorted(workdir.iterdir()):
        if f.suffix.lower() in keep and f.stat().st_size > 0 and not f.name.endswith(".part"):
            target = job.path(f.name)
            f.replace(target)
            outs.append(target)
    shutil.rmtree(workdir, ignore_errors=True)
    if not outs:
        raise ToolError("İndirme başarısız.\n" + "\n".join(errors) if errors else "Hiç dosya indirilemedi.")
    note_lines = [f"{len(outs)} dosya indirildi."]
    if errors:
        note_lines.append("Bazıları indirilemedi:\n" + "\n".join(errors))
    note_lines.append("Hatırlatma: yalnızca indirme hakkınız olan içerikleri indirin.")
    return Result(zip_if_many(job, outs, "indirilenler.zip"), note="\n".join(note_lines))
