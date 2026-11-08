@echo off
chcp 65001 >nul
title Donusturucu kurulumu
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kurulum\windows.ps1"
if errorlevel 1 (
  echo.
  echo Kurulum basarisiz oldu. Ayrinti: %LOCALAPPDATA%\Donusturucu\kurulum.log
)
echo.
pause
