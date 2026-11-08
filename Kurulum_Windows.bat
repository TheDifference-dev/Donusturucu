@echo off
chcp 65001 >nul
title Donusturucu kurulumu
if not exist "%~dp0kurulum\windows.ps1" (
  echo.
  echo  HATA: Kurulum dosyalari bulunamadi.
  echo  ZIP dosyasini once AYIKLAYIN: ZIP'e sag tiklayin ^> "Tumunu ayikla" ^> "Ayikla".
  echo  Sonra ayiklanan klasordeki Kurulum_Windows dosyasina cift tiklayin.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kurulum\windows.ps1"
if errorlevel 1 (
  echo.
  echo Kurulum basarisiz oldu. Ayrinti: %LOCALAPPDATA%\Donusturucu\kurulum.log
)
echo.
pause
