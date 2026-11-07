@echo off
rem Export the Godot project to build/web (single-threaded, any static host),
rem then pre-compress the big files so the server can send them gzipped.
setlocal
cd /d "%~dp0..\game"
if not exist "..\build\web" mkdir "..\build\web"
"D:\dev\tools\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . --export-release "Web" ../build/web/index.html
python "%~dp0gzip_web.py"
