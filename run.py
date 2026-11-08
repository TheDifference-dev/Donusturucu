"""Dönüştürücü — başlatıcı. Yerel sunucuyu açar ve uygulamayı kendi penceresinde gösterir.
Kullanım:  python run.py            (pencere açar)
           python run.py --no-window (sadece sunucu; adresi tarayıcıda açın)"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from donusturucu import core  # noqa: E402

# pythonw.exe / .app ile açılınca konsol yok: çıktıları günlük dosyasına yönlendir
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


def open_window(url: str):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()

    url = already_running()
    if url:   # ikinci kez çift tıklanırsa yeni pencere aç, yeni sunucu başlatma
        if not a.no_window:
            open_window(url)
        return

    from waitress import serve
    from donusturucu.server import create_app, watchdog

    port = free_port(a.port)
    url = f"http://127.0.0.1:{port}/"
    root = Path(tempfile.gettempdir()) / "donusturucu_dosyalar"
    import shutil
    shutil.rmtree(root, ignore_errors=True)   # önceki oturumun geçici dosyaları
    app = create_app(core.FileStore(root))
    LOCK.write_text(json.dumps({"url": url, "pid": os.getpid()}))
    if not a.no_window:
        watchdog(timeout=120)
        threading.Timer(0.8, open_window, args=(url,)).start()
    print(f"{core.APP_NAME} çalışıyor: {url}  (kapatmak için pencereyi kapatın / Ctrl+C)")
    try:
        serve(app, host="127.0.0.1", port=port, threads=8, channel_timeout=3600,
              max_request_body_size=4 * 1024 ** 3)
    finally:
        try:
            LOCK.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
