@echo off
cd /d "%~dp0"

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building self-contained executable...
pyinstaller --onefile --windowed ^
    --name "HentaiMangaReader" ^
    --icon app_icon.ico ^
    --add-data "app_icon.ico;." ^
    --hidden-import=PIL._tkinter_finder ^
    --collect-all customtkinter ^
    app.py

echo.
echo Done! Executable: dist\HentaiMangaReader.exe
echo Progress/settings are saved to: %%APPDATA%%\HentaiMangaReader\
echo.
echo Copying to Desktop...
copy "dist\HentaiMangaReader.exe" "%USERPROFILE%\Desktop\HentaiMangaReader.exe"
if %ERRORLEVEL%==0 (echo Success! HentaiMangaReader.exe is on your desktop.) else (echo Copy failed - manually copy from dist folder.)
echo.
pause
