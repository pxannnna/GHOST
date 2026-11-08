@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-demo.ps1" -Launch
if errorlevel 1 pause
