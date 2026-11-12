@echo off
rem Kontrollsenter for Windows – dobbeltklikk for å installere eller oppdatere.
chcp 65001 >nul
title Kontrollsenter – installasjon
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1"
echo.
pause
