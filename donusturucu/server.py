"""Yerel web sunucusu (yalnızca 127.0.0.1). Arayüz static/ klasöründe."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path

import pymupdf as fitz
from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from . import core
from .core import FileStore, Job, ToolError, capabilities, load_settings, save_settings
from .pdf_tools import decode_data_url, form_fields
from .registry import BY_ID, public_catalog

STATIC = Path(__file__).parent / "static"
LAST_PING = [time.time()]


def default_output_dir() -> Path:
    s = load_settings().get("output_dir")
    if s:
        return Path(s)
    dl = Path.home() / "Downloads"
    return (dl if dl.exists() else Path.home()) / "Dönüştürücü"


def create_app(store: FileStore | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 ** 3   # 4 GB (videolar için)
    st = store or FileStore()
    app.store = st

    @app.after_request
    def no_cache(r):
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:p>")
    def static_files(p):
        return send_from_directory(STATIC, p)

    @app.get("/api/catalog")
    def catalog():
        return jsonify(public_catalog())

    @app.get("/api/status")
    def status():
        c = capabilities()
        c["cikti_klasoru"] = str(default_output_dir())
        return jsonify(c)

    @app.post("/api/settings")
    def settings():
        data = request.get_json(force=True) or {}
        allowed = {k: v for k, v in data.items() if k in ("anthropic_api_key", "output_dir")}
        if "output_dir" in allowed and allowed["output_dir"]:
            Path(allowed["output_dir"]).expanduser().mkdir(parents=True, exist_ok=True)
        save_settings(allowed)
        return jsonify(ok=True)

    @app.post("/api/ping")
    def ping():
        LAST_PING[0] = time.time()
        return jsonify(ok=True)

    @app.post("/api/upload")
    def upload():
        st.cleanup()
        out = []
        for f in request.files.getlist("files"):
            sf = st.add_bytes(f.filename or "dosya", f.read())
            out.append(_describe(sf))
        for d in (request.form.getlist("dataurl") or []):   # imza / kamera görüntüsü
            name, _, data = d.partition("|")
            sf = st.add_bytes(name or "gorsel.png", decode_data_url(data))
            out.append(_describe(sf))
        return jsonify(out)

    def _describe(sf):
        d = sf.public()
        if sf.path.suffix.lower() == ".pdf":
            try:
                doc = fitz.open(sf.path)
                d["pages"] = doc.page_count
                d["encrypted"] = bool(doc.needs_pass)
                if not doc.needs_pass:
                    d["sizes"] = [[round(p.rect.width, 2), round(p.rect.height, 2)] for p in doc]
            except Exception:
                d["pages"] = 0
                d["broken"] = True
        return d

    @app.get("/api/file/<fid>/page/<int:n>")
    def page_png(fid, n):
        sf = st.get(fid)
        w = min(int(request.args.get("w", 220)), 2000)
        try:
            if sf.path.suffix.lower() == ".pdf":
                doc = fitz.open(sf.path)
                pg = doc[n]
            else:
                doc = fitz.open(sf.path)
                pg = doc[0]
        except Exception:
            abort(404)
        zoom = w / pg.rect.width
        pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        cache = sf.path.parent / f"_p{n}_{w}.png"
        if not cache.exists():
            pix.save(cache)
        return send_file(cache, mimetype="image/png")

    @app.get("/api/file/<fid>/fields")
    def fields(fid):
        return jsonify(form_fields(st.get(fid).path))

    @app.post("/api/run/<tool_id>")
    def run_tool(tool_id):
        tool = BY_ID.get(tool_id)
        if not tool:
            return jsonify(error="Bilinmeyen araç"), 404
        body = request.get_json(force=True) or {}
        try:
            inputs = [st.get(i).path for i in body.get("file_ids", [])]
            extra = {k: st.get(v).path for k, v in (body.get("extra") or {}).items() if v}
            out = st.new_workdir()
            job = Job(inputs=inputs, opts=body.get("opts") or {}, out=out, store=st, extra=extra)
            t0 = time.time()
            res = tool["fn"](job)
            files = [st.add_path(p).public() for p in res.files]
            shutil.rmtree(out, ignore_errors=True)
            return jsonify(files=files, text=res.text, html=res.html, note=res.note,
                           seconds=round(time.time() - t0, 1))
        except ToolError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:
            traceback.print_exc()
            return jsonify(error=f"Beklenmeyen hata: {type(e).__name__}: {e}"), 500

    @app.get("/api/download/<fid>")
    def download(fid):
        sf = st.get(fid)
        inline = request.args.get("inline") == "1"
        return send_file(sf.path, as_attachment=not inline, download_name=sf.name)

    @app.post("/api/save/<fid>")
    def save_to_folder(fid):
        """Çıktıyı ayarlanan klasöre (varsayılan: İndirilenler/Dönüştürücü) kaydeder."""
        sf = st.get(fid)
        d = default_output_dir()
        d.mkdir(parents=True, exist_ok=True)
        target = d / sf.name
        i = 2
        while target.exists():
            target = d / f"{Path(sf.name).stem} ({i}){Path(sf.name).suffix}"
            i += 1
        shutil.copy2(sf.path, target)
        if (request.get_json(silent=True) or {}).get("reveal"):
            reveal(target)
        return jsonify(path=str(target))

    @app.post("/api/open-folder")
    def open_folder():
        d = default_output_dir()
        d.mkdir(parents=True, exist_ok=True)
        reveal(d)
        return jsonify(ok=True)

    @app.errorhandler(ToolError)
    def tool_err(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(413)
    def too_big(e):
        return jsonify(error="Dosya çok büyük (en fazla 4 GB)."), 413

    return app


def reveal(path: Path):
    try:
        if core.SYSTEM == "Windows":
            if path.is_file():
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                os.startfile(str(path))  # type: ignore[attr-defined]
        elif core.SYSTEM == "Darwin":
            subprocess.Popen(["open", "-R", str(path)] if path.is_file() else ["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])
    except Exception:
        pass


def watchdog(timeout=90):
    """Pencere kapandıktan sonra (ping gelmezse) sunucuyu kapatır."""
    def loop():
        while True:
            time.sleep(10)
            if time.time() - LAST_PING[0] > timeout:
                os._exit(0)
    threading.Thread(target=loop, daemon=True).start()
