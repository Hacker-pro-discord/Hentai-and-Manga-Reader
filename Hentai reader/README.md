# Hentai Manga Reader

A desktop app for browsing and reading manga from MangaDex and NHentai. Features a dark UI, popup reader, progress saving, and auto-play.

## Platforms

| Platform | Support |
|----------|---------|
| **Windows** | ✅ Full support — use the pre-built EXE or run from source |
| **macOS** | ✅ Run from source (`python app.py`) |
| **Linux** | ✅ Run from source (`python app.py`) |

The packaged `.exe` is **Windows only**. On macOS and Linux, run the Python app directly.

---

## Executable (Windows)

**EXE location (after building):**
```
dist/HentaiMangaReader.exe
```

To distribute the EXE, upload `dist/HentaiMangaReader.exe` to the GitHub Releases section when you create a new release.

To build the executable:
1. Install dependencies: `pip install -r requirements.txt pyinstaller`
2. Run: `build_exe.bat`  
   Or: `python -m PyInstaller --onefile --windowed --name "HentaiMangaReader" --icon app_icon.ico --add-data "app_icon.ico;." --collect-all customtkinter app.py`
3. Copy `dist/HentaiMangaReader.exe` to your desktop or anywhere you like

The EXE is self-contained — no Python installation required.

---

## Features

- **Dual sources**: NHentai (default) and MangaDex
- **Search & browse** with cover images
- **Load more** — scroll to bottom and click to load more results
- **Popup reader** — full-page view with Previous/Next
- **Auto-play** — configurable speed (seconds between pages)
- **Progress saving** — resumes where you left off
- **Adult content** — filter by source and preference

## Requirements (run from source)

- Python 3.10+
- Internet connection

## Quick Start (from source)

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the app:
   ```
   python app.py
   ```

## Usage

1. Choose **NHentai** or **MangaDex** from the source dropdown
2. Browse popular manga or search by title
3. Scroll down and click **Load more** for additional results
4. Click a manga cover to view chapters
5. Click **Resume** to continue from last position, or pick a chapter
6. Reader opens in a popup — use Previous/Next or arrow keys
7. Use **Auto ▶** with the speed (seconds) to auto-advance pages

## Data & Storage

- **MangaDex** — [API terms](https://api.mangadex.org/docs/2-limitations/)
- **NHentai** — Public API
- Progress is stored in `%APPDATA%\HentaiMangaReader\` (Windows) or next to the script when run from source

## License

MIT
