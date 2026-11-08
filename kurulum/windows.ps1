# Dönüştürücü — Windows kurulumu
# Ne yapar: Python'u (yoksa) kurar, uygulamayı %LOCALAPPDATA%\Donusturucu klasörüne kopyalar,
# bağımlılıkları kurar ve masaüstüne + Başlat menüsüne "Dönüştürücü" kısayolu koyar.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Src  = Split-Path -Parent $PSScriptRoot          # converter klasörü
$Home_ = Join-Path $env:LOCALAPPDATA 'Donusturucu'
$App  = Join-Path $Home_ 'app'
$Venv = Join-Path $Home_ 'venv'
$Log  = Join-Path $Home_ 'kurulum.log'
New-Item -ItemType Directory -Force -Path $Home_ | Out-Null
Start-Transcript -Path $Log -Force | Out-Null

function Adim($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

function Find-Python {
    foreach ($c in @(@('py','-3.12'), @('py','-3.13'), @('py','-3.11'), @('py','-3'), @('python'))) {
        try {
            $v = & $c[0] $c[1..9] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) {
                $p = [version]$v.Trim()
                if ($p -ge [version]'3.10') { return ,$c }
            }
        } catch { }
    }
    return $null
}

Adim 'Python aranıyor'
$Py = Find-Python
if (-not $Py) {
    Write-Host 'Python 3.10+ bulunamadı. winget ile Python 3.12 (yalnızca bu kullanıcı için) kuruluyor…'
    try {
        winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    } catch {
        Write-Host 'winget kullanılamadı.' -ForegroundColor Yellow
    }
    $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')
    $Py = Find-Python
    if (-not $Py) {
        Start-Process 'https://www.python.org/downloads/windows/'
        throw 'Python kurulamadı. Açılan sayfadan Python 3.12 indirip kurun ("Add python.exe to PATH" kutusunu işaretleyin), sonra bu kurulumu tekrar çalıştırın.'
    }
}
Write-Host ("Kullanılan Python: " + ($Py -join ' '))

Adim 'Uygulama dosyaları kopyalanıyor'
if (Test-Path $App) { Remove-Item -Recurse -Force $App }
New-Item -ItemType Directory -Force -Path $App | Out-Null
Copy-Item -Recurse -Force (Join-Path $Src 'donusturucu') $App
Copy-Item -Force (Join-Path $Src 'run.py'), (Join-Path $Src 'requirements.txt') $App
Get-ChildItem -Path $App -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force

Adim 'Sanal ortam hazırlanıyor'
if (-not (Test-Path (Join-Path $Venv 'Scripts\python.exe'))) {
    & $Py[0] $Py[1..9] -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Sanal ortam oluşturulamadı.' }
}
$VPy = Join-Path $Venv 'Scripts\python.exe'
$VPyw = Join-Path $Venv 'Scripts\pythonw.exe'

Adim 'Bağımlılıklar kuruluyor (ilk seferde birkaç dakika sürebilir)'
& $VPy -m pip install --upgrade pip --disable-pip-version-check -q
& $VPy -m pip install -r (Join-Path $App 'requirements.txt') --disable-pip-version-check --progress-bar on
if ($LASTEXITCODE -ne 0) { throw 'Paketler kurulamadı. İnternet bağlantısını kontrol edip tekrar deneyin.' }
& $VPy -c "import pymupdf, pdf2docx, pikepdf, flask, waitress, imageio_ffmpeg; imageio_ffmpeg.get_ffmpeg_exe(); print('Bağımlılık kontrolü: OK')"
if ($LASTEXITCODE -ne 0) { throw 'Kurulum doğrulaması başarısız.' }

Adim 'Kısayollar oluşturuluyor'
$Name = 'Dönüştürücü'
$Icon = Join-Path $App 'donusturucu\static\icon.ico'
$Shell = New-Object -ComObject WScript.Shell
$Targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) "$Name.lnk"),
    (Join-Path ([Environment]::GetFolderPath('Programs')) "$Name.lnk")
)
foreach ($lnk in $Targets) {
    $s = $Shell.CreateShortcut($lnk)
    $s.TargetPath = $VPyw
    $s.Arguments = '"' + (Join-Path $App 'run.py') + '"'
    $s.WorkingDirectory = $App
    $s.IconLocation = $Icon
    $s.Description = 'PDF ve video dönüştürücü'
    $s.Save()
    Write-Host "Oluşturuldu: $lnk"
}

Stop-Transcript | Out-Null
Write-Host "`nKurulum tamamlandı. Masaüstündeki '$Name' simgesine çift tıklayın." -ForegroundColor Green
Write-Host "Kaldırmak için: '$Home_' klasörünü ve masaüstündeki kısayolu silin."
