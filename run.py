"""Dönüştürücü — başlatıcı. Yerel sunucuyu açar ve uygulamayı kendi penceresinde gösterir.
Kullanım:  python run.py             (masaüstü penceresi; pywebview yoksa Edge/Chrome uygulama penceresi)
           python run.py --browser   (Edge/Chrome uygulama penceresi)
           python run.py --no-window (sadece sunucu; adresi tarayıcıda açın)
           python run.py --selftest  (paket doğrulaması: birkaç aracı çalıştırıp çıkar)"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.request
import webbrowser
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from donusturucu import core  # noqa: E402

# pythonw.exe / .exe / .app ile açılınca konsol yok: çıktıları günlük dosyasına yönlendir
if sys.stdout is None or sys.stderr is None:
    _log = open(core.config_dir() / "calisma.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _log
    if sys.stderr is None:
        sys.stderr = _log

LOCK = core.config_dir() / "calisan.json"


def free_port(preferred=8765) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 50)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def already_running() -> str | None:
    try:
        info = json.loads(LOCK.read_text())
        url = info["url"]
        urllib.request.urlopen(url + "api/catalog", timeout=1.5)
        return url
    except Exception:
        return None


def open_browser_window(url: str):
    """Edge/Chrome'u adres çubuğu olmayan 'uygulama' penceresi olarak açar; yoksa varsayılan tarayıcı."""
    browser = core.find_browser()
    if browser:
        prof = core.config_dir() / "pencere_profili"
        kw = {}
        if core.SYSTEM == "Windows":
            kw["creationflags"] = 0x00000008  # DETACHED_PROCESS
        try:
            subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={prof}", "--no-first-run",
                              "--no-default-browser-check", "--window-size=1280,860"], **kw)
            return
        except Exception:
            pass
    webbrowser.open(url)


def start_server(port_pref: int):
    from waitress import create_server
    from donusturucu.server import create_app

    port = free_port(port_pref)
    url = f"http://127.0.0.1:{port}/"
    root = Path(tempfile.gettempdir()) / "donusturucu_dosyalar"
    shutil.rmtree(root, ignore_errors=True)   # önceki oturumun geçici dosyaları
    app = create_app(core.FileStore(root))
    srv = create_server(app, host="127.0.0.1", port=port, threads=8, channel_timeout=3600,
                        max_request_body_size=4 * 1024 ** 3)
    LOCK.write_text(json.dumps({"url": url, "pid": os.getpid()}))
    return app, srv, url


class DesktopApi:
    """Pencere içindeki JavaScript'in çağırdığı yerel işlevler (Kaydet iletişim kutusu, dosyayı aç)."""

    def __init__(self, app):
        self._app = app
        self._win = None

    def save_as(self, fid, name):
        import webview
        src = self._app.store.get(fid).path
        res = self._win.create_file_dialog(webview.FileDialog.SAVE, save_filename=name,
                                           directory=str(Path.home() / "Desktop"))
        if not res:
            return None
        target = res if isinstance(res, str) else res[0]
        shutil.copy2(src, target)
        return target

    def open_file(self, fid):
        p = self._app.store.get(fid).path
        if core.SYSTEM == "Windows":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif core.SYSTEM == "Darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return True

    def open_url(self, url):
        webbrowser.open(url)
        return True


def run_desktop(app, srv, url) -> bool:
    try:
        import webview
    except Exception:
        return False
    threading.Thread(target=srv.run, daemon=True).start()
    api = DesktopApi(app)
    icon = Path(core.resource_dir()) / "static" / ("icon.ico" if core.SYSTEM == "Windows" else "icon.png")
    try:
        win = webview.create_window(core.APP_NAME, url, js_api=api, width=1280, height=860,
                                    min_size=(760, 560), text_select=True)
        api._win = win
        storage = core.config_dir() / "pencere"
        webview.start(private_mode=False, storage_path=str(storage), icon=str(icon))
    except Exception as e:   # WebView2 yoksa vb. → tarayıcı penceresine düş
        print("Masaüstü penceresi açılamadı:", e)
        return False
    return True


def selftest() -> int:
    """Paketlenmiş uygulamanın bileşenlerini (font, ffmpeg, docx şablonu, OCR motoru) gerçekten çalıştırır."""
    import io
    import pymupdf as fitz
    from donusturucu.server import create_app
    app = create_app(core.FileStore())
    c = app.test_client()
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((72, 80), "Test sayfası İstanbul ğüşıöç", fontsize=14, fontname=core.add_font(pg))
    pdf = doc.tobytes()
    ff = core.find_ffmpeg()
    tmp = Path(tempfile.mkdtemp())
    wav = tmp / "ton.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=2", "-shortest", "-c:a", "aac",
                    "-c:v", "mpeg4", str(wav)], check=True, **({"creationflags": 0x08000000} if core.SYSTEM == "Windows" else {}))
    up = c.post("/api/upload", data={"files": [(io.BytesIO(pdf), "test.pdf"), (wav.open("rb"), "ton.mp4")]},
                content_type="multipart/form-data").get_json()
    pid, vid = up[0]["id"], up[1]["id"]
    checks = [
        ("pdf_to_word", [pid], {}), ("compress", [pid], {}), ("page_numbers", [pid], {}),
        ("pdf_to_excel", [pid], {}), ("pdf_to_ppt", [pid], {}), ("pdf_to_markdown", [pid], {}),
        ("watermark", [pid], {"text": "GİZLİ"}), ("protect", [pid], {"password": "1", "password2": "1"}),
        ("video_to_audio", [vid], {"format": "mp3"}), ("summarize", [pid], {"engine": "offline"}),
    ]
    bad = 0
    for tid, ids, opts in checks:
        r = c.post(f"/api/run/{tid}", json={"file_ids": ids, "opts": opts})
        j = r.get_json()
        ok = r.status_code == 200 and j.get("files")
        bad += 0 if ok else 1
        print(("OK   " if ok else "HATA ") + tid + ("" if ok else f" → {j.get('error')}"), flush=True)
    r = c.get("/")
    print(("OK   " if r.status_code == 200 else "HATA ") + "arayüz", flush=True)
    bad += r.status_code != 200
    print("SONUÇ:", "BAŞARILI" if not bad else f"{bad} hata", flush=True)
    return 1 if bad else 0


def main():
    multiprocessing.freeze_support()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()

    if a.selftest:
        sys.exit(selftest())

    url = already_running()
    if url and (a.browser or a.no_window):
        if not a.no_window:
            open_browser_window(url)
        return

    app, srv, url = start_server(a.port)
    print(f"{core.APP_NAME} çalışıyor: {url}", flush=True)
    try:
        if not a.no_window and not a.browser and run_desktop(app, srv, url):
            return   # pencere kapandı → çık
        if not a.no_window:
            from donusturucu.server import watchdog
            watchdog(timeout=120)
            threading.Timer(0.8, open_browser_window, args=(url,)).start()
        srv.run()
    finally:
        try:
            LOCK.unlink()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    main()
