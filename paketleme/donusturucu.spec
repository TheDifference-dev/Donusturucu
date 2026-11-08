# PyInstaller tanımı — Windows'ta: pyinstaller paketleme/donusturucu.spec
# Çıktı: dist/Donusturucu/Donusturucu.exe (klasör kurulumu; Inno Setup ile kurulum exe'sine çevrilir)
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
datas, binaries, hidden = [(str(ROOT / "donusturucu" / "static"), "donusturucu/static")], [], []
for pkg in ["pymupdf", "pymupdf_fonts", "pymupdf4llm", "pymupdf_layout", "imageio_ffmpeg", "docx", "pptx",
            "pdf2docx", "openpyxl", "pikepdf", "webview", "deep_translator", "anthropic", "certifi"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception as e:
        print("atlandı:", pkg, e)
hidden += ["waitress", "flask", "cv2", "numpy", "PIL.ImageCms", "donusturucu.server", "donusturucu.registry"]
if sys.platform == "win32":
    hidden += ["win32com", "win32com.client", "pythoncom", "pywintypes", "clr_loader", "pythonnet"]

a = Analysis([str(ROOT / "run.py")], pathex=[str(ROOT)], binaries=binaries, datas=datas,
             hiddenimports=hidden, excludes=["tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6", "PySide6"],
             noarchive=False)
pyz = PYZ(a.pure)
icon = str(ROOT / "donusturucu" / "static" / ("icon.ico" if sys.platform == "win32" else "icon.png"))
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Donusturucu", console=False, icon=icon,
          version=str(ROOT / "paketleme" / "surum.txt") if sys.platform == "win32" else None, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Donusturucu", upx=False)
