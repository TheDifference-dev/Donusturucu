#!/bin/bash
# Dönüştürücü — macOS kurulumu
# Ne yapar: uygulamayı ~/Library/Application Support/Donusturucu altına kurar,
# bağımlılıkları yükler ve Masaüstüne "Dönüştürücü.app" koyar.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="$HOME/Library/Application Support/Donusturucu"
APP="$HOME_DIR/app"; VENV="$HOME_DIR/venv"
mkdir -p "$HOME_DIR"
exec > >(tee "$HOME_DIR/kurulum.log") 2>&1

step(){ printf "\n==> %s\n" "$1"; }

step "Python aranıyor"
PY=""
for c in python3.12 python3.13 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2]>=(3,10) else 1)' 2>/dev/null; then PY="$(command -v "$c")"; break; fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "Python 3.10+ yok; Homebrew ile python@3.12 kuruluyor…"
    brew install python@3.12
    PY="$(brew --prefix)/bin/python3.12"
  else
    open "https://www.python.org/downloads/macos/"
    echo "Python 3.10+ bulunamadı. Açılan sayfadan Python 3.12'yi kurup bu dosyayı tekrar çalıştırın."
    exit 1
  fi
fi
echo "Kullanılan Python: $PY"

step "Uygulama dosyaları kopyalanıyor"
rm -rf "$APP"; mkdir -p "$APP"
cp -R "$SRC/donusturucu" "$SRC/run.py" "$SRC/requirements.txt" "$APP/"
find "$APP" -name "__pycache__" -type d -prune -exec rm -rf {} +

step "Sanal ortam ve bağımlılıklar (ilk seferde birkaç dakika sürebilir)"
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip -q --disable-pip-version-check
"$VENV/bin/python" -m pip install -r "$APP/requirements.txt" --disable-pip-version-check
"$VENV/bin/python" -c "import pymupdf, pdf2docx, pikepdf, flask, waitress, imageio_ffmpeg; imageio_ffmpeg.get_ffmpeg_exe(); print('Bağımlılık kontrolü: OK')"

step "Masaüstü uygulaması oluşturuluyor"
BUNDLE="$HOME/Desktop/Dönüştürücü.app"
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"
cat > "$BUNDLE/Contents/MacOS/Donusturucu" <<EOS
#!/bin/bash
cd "$APP"
exec "$VENV/bin/python" "$APP/run.py"
EOS
chmod +x "$BUNDLE/Contents/MacOS/Donusturucu"
ICONSET="$(mktemp -d)/icon.iconset"; mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512; do
  sips -z $s $s "$APP/donusturucu/static/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1 || true
done
iconutil -c icns "$ICONSET" -o "$BUNDLE/Contents/Resources/icon.icns" 2>/dev/null || true
cat > "$BUNDLE/Contents/Info.plist" <<EOS
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Dönüştürücü</string>
  <key>CFBundleDisplayName</key><string>Dönüştürücü</string>
  <key>CFBundleIdentifier</key><string>local.donusturucu</string>
  <key>CFBundleExecutable</key><string>Donusturucu</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
EOS
touch "$BUNDLE"
echo
echo "Kurulum tamamlandı. Masaüstündeki 'Dönüştürücü' uygulamasına çift tıklayın."
echo "Kaldırmak için: '$HOME_DIR' klasörünü ve masaüstündeki uygulamayı silin."
