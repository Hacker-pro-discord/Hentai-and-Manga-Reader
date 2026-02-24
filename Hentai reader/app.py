"""Hentai Manga Reader - Simple desktop app for reading manga from MangaDex."""

import sys
import customtkinter as ctk
from tkinter import messagebox
from PIL import Image
import io
import json
import os
import threading

from manga_api import MangaDexAPI, MangaResult, ChapterInfo
from nhentai_api import NHentaiAPI

def _get_base_path():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def _get_data_path():
    if getattr(sys, "frozen", False):
        data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HentaiMangaReader")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    return os.path.dirname(os.path.abspath(__file__))

_APP_DIR = _get_base_path()
_DATA_DIR = _get_data_path()
PROGRESS_PATH = os.path.join(_DATA_DIR, "progress.json")
ICON_PATH = os.path.join(_get_base_path(), "app_icon.ico")


def _load_progress() -> dict:
    try:
        if os.path.exists(PROGRESS_PATH):
            with open(PROGRESS_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"mangadex": {}, "nhentai": {}}


def get_progress(manga_id: str, source: str) -> tuple[str | None, int]:
    """Return (chapter_id, page_index) for manga, or (None, 0) if none."""
    data = _load_progress()
    src = "nhentai" if source == "nhentai" else "mangadex"
    if src not in data or manga_id not in data[src]:
        return None, 0
    val = data[src][manga_id]
    if src == "nhentai":
        return manga_id, int(val) if isinstance(val, (int, float)) else 0
    if isinstance(val, dict):
        if "chapter_id" in val:
            page = val.get("page_index", 0)
            return val["chapter_id"], int(page) if isinstance(page, (int, float)) else 0
        for ch_id, page in val.items():
            return ch_id, int(page) if isinstance(page, (int, float)) else 0
    return None, 0


def _save_progress(data: dict) -> None:
    try:
        with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# Dark theme to match reference
BG_DARK = "#0d0d0d"
BG_CARD = "#1a1a1a"
TEXT_WHITE = "#ffffff"
TEXT_GRAY = "#a0a0a0"
BORDER_GRAY = "#333333"
ACCENT = "#4a9eff"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ReaderPopup(ctk.CTkToplevel):
    """Popup window for reading manga pages. Image fits entirely in view."""

    def __init__(
        self,
        parent: "MangaReaderApp",
        urls: list[str],
        chapter: ChapterInfo,
        manga_id: str = "",
        source: str = "mangadex",
        initial_page: int = 0,
    ):
        super().__init__(parent)
        self.parent_app = parent
        self.urls = urls
        self.chapter_id = chapter.id
        self.manga_id = manga_id
        self.source = source
        self.page_index = max(0, min(initial_page, len(urls) - 1)) if urls else 0

        self.title(f"{parent.current_manga.title} - Ch. {chapter.chapter}")
        self.geometry("1100x850")
        self.transient(parent)
        if os.path.exists(ICON_PATH):
            self.iconbitmap(ICON_PATH)
        self.minsize(800, 600)
        self.configure(fg_color=BG_DARK)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Nav bar
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        nav.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(
            nav, text="← Previous", command=self._prev, width=100, height=36,
            fg_color=BG_CARD, border_width=1, border_color=BORDER_GRAY,
        ).grid(row=0, column=0, padx=(0, 12))

        self.page_label = ctk.CTkLabel(nav, text="", font=ctk.CTkFont(size=14), text_color=TEXT_GRAY)
        self.page_label.grid(row=0, column=1, padx=12)

        ctk.CTkButton(
            nav, text="Next →", command=self._next, width=100, height=36,
            fg_color=ACCENT, hover_color="#3a8eef",
        ).grid(row=0, column=2, sticky="w", padx=(0, 24))

        self._autoplay_var = ctk.BooleanVar(value=False)
        self._autoplay_job = None
        self._autoplay_interval = 5000
        ctk.CTkLabel(nav, text="Auto (sec):", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY).grid(row=0, column=3, padx=(24, 4))
        self._autoplay_entry = ctk.CTkEntry(
            nav, width=45, height=32, placeholder_text="5",
            fg_color=BG_CARD, border_color=BORDER_GRAY,
        )
        self._autoplay_entry.insert(0, "5")
        self._autoplay_entry.grid(row=0, column=4, padx=2)
        self._autoplay_btn = ctk.CTkButton(
            nav, text="Auto ▶", width=80, height=36,
            fg_color=BG_CARD, border_width=1, border_color=BORDER_GRAY,
            command=self._toggle_autoplay,
        )
        self._autoplay_btn.grid(row=0, column=5, padx=(8, 0))

        # Image area
        self.img_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.img_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.img_frame.grid_columnconfigure(0, weight=1)
        self.img_frame.grid_rowconfigure(0, weight=1)

        self.img_label = ctk.CTkLabel(
            self.img_frame, text="Loading...", text_color=TEXT_GRAY, font=ctk.CTkFont(size=14)
        )
        self.img_label.grid(row=0, column=0)

        self.bind("<Right>", lambda e: self._next())
        self.bind("<Left>", lambda e: self._prev())
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._resize_job = None

        self._update_label()
        self._load_page()

    def _on_close(self):
        self._save_progress()
        self._cancel_autoplay()
        self.destroy()

    def _get_autoplay_interval(self) -> int:
        try:
            v = int(self._autoplay_entry.get().strip() or "5")
            return max(1, min(60, v)) * 1000
        except ValueError:
            return 5000

    def _toggle_autoplay(self):
        self._autoplay_var.set(not self._autoplay_var.get())
        if self._autoplay_var.get():
            self._autoplay_interval = self._get_autoplay_interval()
            self._autoplay_btn.configure(text="Stop ■", fg_color="#c44")
            self._schedule_autoplay()
        else:
            self._autoplay_btn.configure(text="Auto ▶", fg_color=BG_CARD)
            self._cancel_autoplay()

    def _cancel_autoplay(self):
        if self._autoplay_job:
            self.after_cancel(self._autoplay_job)
            self._autoplay_job = None

    def _schedule_autoplay(self):
        self._cancel_autoplay()
        if self._autoplay_var.get() and self.page_index < len(self.urls) - 1:
            self._autoplay_interval = self._get_autoplay_interval()
            self._autoplay_job = self.after(self._autoplay_interval, self._autoplay_advance)

    def _autoplay_advance(self):
        self._autoplay_job = None
        if not self._autoplay_var.get() or self.page_index >= len(self.urls) - 1:
            if self.page_index >= len(self.urls) - 1:
                self._autoplay_var.set(False)
                self._autoplay_btn.configure(text="Auto ▶", fg_color=BG_CARD)
            return
        self.page_index += 1
        self._update_label()
        self._save_progress()
        self._load_page()
        self._schedule_autoplay()

    def _prev(self):
        if self.page_index > 0:
            self.page_index -= 1
            self._update_label()
            self._save_progress()
            self._load_page()
            self._schedule_autoplay()

    def _next(self):
        if self.page_index < len(self.urls) - 1:
            self.page_index += 1
            self._update_label()
            self._save_progress()
            self._load_page()
            self._schedule_autoplay()

    def _update_label(self):
        self.page_label.configure(text=f"Page {self.page_index + 1} of {len(self.urls)}")

    def _save_progress(self):
        if not self.manga_id:
            return
        data = _load_progress()
        src = "nhentai" if self.source == "nhentai" else "mangadex"
        if src not in data:
            data[src] = {}
        if src == "nhentai":
            data[src][self.manga_id] = self.page_index
        else:
            data[src][self.manga_id] = {"chapter_id": self.chapter_id, "page_index": self.page_index}
        _save_progress(data)

    def _load_page(self):
        idx = self.page_index
        if idx < 0 or idx >= len(self.urls):
            return
        self.img_label.configure(text=f"Loading page {idx+1}...", image=None)
        url = self.urls[idx]
        cache_key = f"{self.chapter_id}_{idx}"
        lbl = self.img_label
        win = self

        def load():
            app = win.parent_app
            if cache_key not in app.image_cache:
                try:
                    api = app.nhentai if getattr(app.current_manga, "source", "") == "nhentai" else app.mangadex
                    data = api.fetch_image(url)
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    app.image_cache[cache_key] = img
                except Exception as e:
                    win.after(0, lambda: lbl.configure(text=f"Failed: {str(e)[:40]}") if lbl.winfo_exists() else None)
                    return
            img = app.image_cache[cache_key]
            win.after(0, lambda: win._display(img))

        threading.Thread(target=load, daemon=True).start()

    def _on_resize(self, event):
        if event.widget != self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self._resize_redisplay)

    def _resize_redisplay(self):
        self._resize_job = None
        cache_key = f"{self.chapter_id}_{self.page_index}"
        if cache_key in self.parent_app.image_cache:
            self._display(self.parent_app.image_cache[cache_key])

    def _display(self, img: Image.Image):
        try:
            if not self.img_label.winfo_exists():
                return
            self.update_idletasks()
            # Fit entire image in window - scale to fit both width and height
            w, h = self.winfo_width(), self.winfo_height()
            if w < 400 or h < 400:
                w, h = 1100, 850
            avail_w = w - 80
            avail_h = h - 120
            ratio_w = avail_w / img.width
            ratio_h = avail_h / img.height
            scale = min(ratio_w, ratio_h, 1.0)
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            if new_w != img.width or new_h != img.height:
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.img_label.configure(image=ctk_img, text="")
            self.img_label._img_ref = (ctk_img, img)
        except Exception:
            self.img_label.configure(text="Failed to display")


class MangaReaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Hentai Manga Reader")
        self.geometry("1400x900")
        self.minsize(1200, 800)
        if os.path.exists(ICON_PATH):
            self.iconbitmap(ICON_PATH)
        self.configure(fg_color=BG_DARK)

        self.mangadex = MangaDexAPI()
        self.nhentai = NHentaiAPI()
        self._current_source = "nhentai"  # Default: hentai source
        self.current_manga: MangaResult | None = None
        self.current_chapters: list[ChapterInfo] = []
        self.view_state = "search"
        self.image_cache: dict[str, Image.Image] = {}
        self.cover_cache: dict[str, Image.Image] = {}
        self._manga_results: list[MangaResult] = []
        self._manga_offset = 0
        self._manga_total = 0
        self._manga_mode = "browse"
        self._manga_query = ""

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header - DISCOVER COMICS style
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=32, pady=(32, 8), sticky="w")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame,
            text="DISCOVER MANGA",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=TEXT_WHITE,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header_frame,
            text="Browse manga & comics. Filter by genre to find your next read.",
            font=ctk.CTkFont(size=14),
            text_color=TEXT_GRAY,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Search and filter bar
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.grid(row=1, column=0, padx=32, pady=(16, 12), sticky="ew")
        filter_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            filter_frame,
            placeholder_text="Search by title...",
            height=40,
            font=ctk.CTkFont(size=14),
            fg_color=BG_CARD,
            border_color=BORDER_GRAY,
            placeholder_text_color=TEXT_GRAY,
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 12), pady=0, sticky="ew")
        self.search_entry.bind("<Return>", lambda e: self._do_search())

        self.source_var = ctk.StringVar(value="NHentai")
        source_menu = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.source_var,
            values=["NHentai", "MangaDex"],
            height=40,
            width=120,
            fg_color=BG_CARD,
            button_color=BORDER_GRAY,
            dropdown_fg_color=BG_CARD,
            command=self._on_source_change,
        )
        source_menu.grid(row=0, column=1, padx=12, pady=0)

        self.genre_var = ctk.StringVar(value="All Genres")
        genre_menu = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.genre_var,
            values=["All Genres", "Romance", "Action", "Comedy", "Drama", "Fantasy"],
            height=40,
            width=120,
            fg_color=BG_CARD,
            button_color=BORDER_GRAY,
            dropdown_fg_color=BG_CARD,
        )
        genre_menu.grid(row=0, column=2, padx=12, pady=0)

        self.english_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            filter_frame,
            text="English only",
            variable=self.english_var,
            font=ctk.CTkFont(size=13),
            text_color=TEXT_GRAY,
        ).grid(row=0, column=3, padx=12, pady=0)

        self.adult_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            filter_frame,
            text="Include adult",
            variable=self.adult_var,
            font=ctk.CTkFont(size=13),
            text_color=TEXT_GRAY,
        ).grid(row=0, column=4, padx=12, pady=0)

        self.search_btn = ctk.CTkButton(
            filter_frame,
            text="Search",
            command=self._do_search,
            width=100,
            height=40,
            fg_color=ACCENT,
            hover_color="#3a8eef",
        )
        self.search_btn.grid(row=0, column=5, padx=(12, 0), pady=0)

        self.back_btn = ctk.CTkButton(
            filter_frame,
            text="← Back",
            command=self._go_back,
            width=90,
            height=40,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER_GRAY,
            text_color=TEXT_WHITE,
        )
        self.back_btn.grid(row=0, column=6, padx=(12, 0), pady=0)
        self.back_btn.grid_remove()

        # Main content area - scrollable grid
        self.main_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_frame.grid(row=2, column=0, padx=32, pady=(0, 24), sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Status label
        self.status_label = ctk.CTkLabel(
            self, text="Search for manga to get started", text_color=TEXT_GRAY, font=ctk.CTkFont(size=13)
        )
        self.status_label.grid(row=3, column=0, padx=32, pady=(0, 24))

        self._load_recommendations()

    def _api(self):
        return self.nhentai if self.source_var.get() == "NHentai" else self.mangadex

    def _api_for_manga(self, manga: MangaResult):
        return self.nhentai if getattr(manga, "source", "mangadex") == "nhentai" else self.mangadex

    def _on_source_change(self, _value=None):
        self._current_source = "nhentai" if self.source_var.get() == "NHentai" else "mangadex"
        self._load_recommendations()

    def _load_recommendations(self):
        """Load popular manga on app start."""
        self.status_label.configure(text="Loading recommendations...")
        threading.Thread(target=self._recommendations_thread, daemon=True).start()

    def _recommendations_thread(self):
        try:
            results, total = self._api().browse_manga(limit=24, offset=0, include_adult=self.adult_var.get())
            self.after(0, lambda: self._show_recommendations(results, total))
        except Exception as e:
            self.after(0, lambda: self._show_search_prompt(str(e)))

    def _show_recommendations(self, results: list[MangaResult], total: int = 0):
        self.view_state = "search"
        self._manga_results = results
        self._manga_offset = len(results)
        self._manga_total = total or len(results)
        self._manga_mode = "browse"
        self._manga_query = ""
        self.status_label.configure(text="Popular manga — Search above to find more")
        self._render_manga_grid(append=False)

    def _show_search_prompt(self, error_msg: str = ""):
        for w in self.main_frame.winfo_children():
            w.destroy()
        text = "Enter a manga title above and click Search.\nResults come from MangaDex."
        if error_msg:
            text = f"Could not load recommendations: {error_msg}\n\n{text}"
        lbl = ctk.CTkLabel(
            self.main_frame,
            text=text,
            font=ctk.CTkFont(size=14),
            text_color=TEXT_GRAY,
        )
        lbl.grid(row=0, column=0, pady=60)

    def _do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showinfo("Search", "Please enter a search term.")
            return
        self.search_btn.configure(state="disabled", text="Searching...")
        self.status_label.configure(text=f"Searching for '{query}'...")
        threading.Thread(
            target=self._search_thread,
            args=(query,),
            daemon=True,
        ).start()

    def _search_thread(self, query: str):
        try:
            results, total = self._api().search_manga(
                query, limit=24, include_adult=self.adult_var.get()
            )
            self.after(0, lambda: self._show_results(results, total, query))
        except Exception as e:
            self.after(0, lambda: self._search_error(str(e)))

    def _search_error(self, msg: str):
        self.search_btn.configure(state="normal", text="Search")
        self.status_label.configure(text="")
        messagebox.showerror("Search Error", msg)

    def _show_results(self, results: list[MangaResult], total: int, query: str):
        self.view_state = "search"
        self.search_btn.configure(state="normal", text="Search")
        self._manga_results = results
        self._manga_offset = len(results)
        self._manga_total = total
        self._manga_mode = "search"
        self._manga_query = query
        self.status_label.configure(text=f"Found {total} result(s) for '{query}'")
        self._render_manga_grid(append=False, empty_msg="No results found. Try a different search.")

    def _load_more(self):
        if self._manga_offset >= self._manga_total:
            return
        self.status_label.configure(text="Loading more...")
        threading.Thread(target=self._load_more_thread, daemon=True).start()

    def _load_more_thread(self):
        try:
            limit = 24
            if self._manga_mode == "browse":
                results, total = self._api().browse_manga(
                    limit=limit, offset=self._manga_offset, include_adult=self.adult_var.get()
                )
            else:
                results, total = self._api().search_manga(
                    self._manga_query,
                    limit=limit,
                    offset=self._manga_offset,
                    include_adult=self.adult_var.get(),
                )
            self.after(0, lambda: self._append_results(results, total))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, lambda: self.status_label.configure(
                text=f"Found {self._manga_total} result(s)" + (f" for '{self._manga_query}'" if self._manga_query else "")
            ))

    def _append_results(self, results: list[MangaResult], total: int):
        self._manga_results.extend(results)
        self._manga_offset = len(self._manga_results)
        self._manga_total = total
        if self._manga_query:
            self.status_label.configure(text=f"Found {total} result(s) for '{self._manga_query}'")
        else:
            self.status_label.configure(text="Popular manga — Search above to find more")
        self._render_manga_grid(append=True)

    def _render_manga_grid(self, append: bool = False, empty_msg: str = "No results found."):
        for w in self.main_frame.winfo_children():
            w.destroy()
        results = self._manga_results
        if not results:
            ctk.CTkLabel(
                self.main_frame, text=empty_msg, text_color=TEXT_GRAY
            ).grid(row=0, column=0, pady=60)
            return
        COLS = 6
        for c in range(COLS):
            self.main_frame.grid_columnconfigure(c, weight=0, minsize=191)
        for i, manga in enumerate(results):
            row, col = divmod(i, COLS)
            card = self._make_manga_card(manga)
            card.grid(row=row, column=col, padx=8, pady=12, sticky="nw")

        if self._manga_offset < self._manga_total:
            load_row = (len(results) + COLS - 1) // COLS
            load_btn = ctk.CTkButton(
                self.main_frame,
                text="Load more",
                command=self._load_more,
                width=140,
                height=40,
                fg_color=ACCENT,
                hover_color="#3a8eef",
            )
            load_btn.grid(row=load_row, column=0, columnspan=COLS, pady=24, sticky="n")

    def _make_manga_card(self, manga: MangaResult) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self.main_frame,
            width=175,
            corner_radius=8,
            fg_color=BG_CARD,
            border_width=0,
        )
        card.grid_propagate(False)

        img_frame = ctk.CTkFrame(
            card, fg_color=BORDER_GRAY, width=175, height=240, corner_radius=6
        )
        img_frame.grid(row=0, column=0, padx=8, pady=(8, 6))
        img_frame.grid_propagate(False)

        img_label = ctk.CTkLabel(
            img_frame,
            text="Loading...",
            width=175,
            height=240,
            text_color=TEXT_GRAY,
            font=ctk.CTkFont(size=12),
        )
        img_label.grid(row=0, column=0)

        def load_cover(lbl=img_label, mid=manga.id):
            if not manga.cover_url:
                self.after(0, lambda l=lbl: l.configure(text="No preview") if l.winfo_exists() else None)
                return
            if mid in self.cover_cache:
                self.after(0, lambda: self._display_cover(lbl, self.cover_cache[mid]))
                return
            try:
                data = self._api_for_manga(manga).fetch_image(manga.cover_url)
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img.thumbnail((350, 480), Image.Resampling.LANCZOS)
                self.cover_cache[mid] = img
                self.after(0, lambda: self._display_cover(lbl, img))
            except Exception:
                self.after(0, lambda l=lbl: l.configure(text="No preview") if l.winfo_exists() else None)

        threading.Thread(target=load_cover, daemon=True).start()

        title_text = (manga.title or "Unknown")[:35]
        if len(manga.title or "") > 35:
            title_text += "..."
        title_lbl = ctk.CTkLabel(
            card,
            text=title_text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_WHITE,
            fg_color="transparent",
            wraplength=160,
            anchor="w",
            justify="left",
            height=36,
        )
        title_lbl.grid(row=1, column=0, padx=8, pady=(0, 2), sticky="w")

        tags_text = " - ".join(manga.tags[:3]) if manga.tags else ""
        tags_lbl = ctk.CTkLabel(
            card,
            text=tags_text,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_GRAY,
            fg_color="transparent",
            wraplength=160,
            anchor="w",
            justify="left",
        )
        tags_lbl.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="w")

        def on_click():
            self._open_manga(manga)

        for widget in (card, img_frame, img_label, title_lbl, tags_lbl):
            widget.bind("<Button-1>", lambda e: on_click())
            widget.configure(cursor="hand2")

        return card

    def _display_cover(self, label: ctk.CTkLabel, img: Image.Image):
        try:
            if not label.winfo_exists():
                return
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(175, 240))
            label.configure(image=ctk_img, text="")
            label._img_ref = (ctk_img, img)
        except Exception:
            label.configure(text="No preview")

    def _open_manga(self, manga: MangaResult):
        self.current_manga = manga
        self.view_state = "chapters"
        self.back_btn.grid()
        self.status_label.configure(text=f"Loading chapters for {manga.title}...")
        threading.Thread(
            target=self._load_chapters_thread,
            args=(manga.id,),
            daemon=True,
        ).start()

    def _load_chapters_thread(self, manga_id: str):
        try:
            api = self.nhentai if self.current_manga and getattr(self.current_manga, "source", "") == "nhentai" else self.mangadex
            chapters = api.get_manga_chapters(manga_id)
            self.after(0, lambda: self._show_chapters(chapters))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, lambda: self.status_label.configure(text=""))

    def _show_chapters(self, chapters: list[ChapterInfo]):
        self.status_label.configure(
            text=f"{self.current_manga.title} - {len(chapters)} chapters"
        )
        for w in self.main_frame.winfo_children():
            w.destroy()

        if not chapters:
            ctk.CTkLabel(
                self.main_frame,
                text="No chapters available.",
                text_color="gray",
            ).grid(row=0, column=0, pady=40)
            return

        self.current_chapters = chapters
        source = getattr(self.current_manga, "source", "mangadex")
        saved_ch_id, saved_page = get_progress(self.current_manga.id, source)

        ctk.CTkLabel(
            self.main_frame,
            text="Select a chapter to read:",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        row_idx = 1
        if saved_ch_id and saved_page >= 0:
            ch_label = next((f"Ch. {c.chapter}" for c in chapters if c.id == saved_ch_id), None)
            if ch_label:
                resume_btn = ctk.CTkButton(
                    self.main_frame,
                    text=f"Resume: {ch_label} (page {saved_page + 1})",
                    command=lambda: self._open_chapter_resume(saved_ch_id, saved_page),
                    anchor="w",
                    height=36,
                    fg_color=ACCENT,
                    hover_color="#3a8eef",
                )
                resume_btn.grid(row=row_idx, column=0, sticky="ew", pady=2)
                row_idx += 1

        for i, ch in enumerate(reversed(chapters)):
            btn = ctk.CTkButton(
                self.main_frame,
                text=f"Ch. {ch.chapter}" + (f" - {ch.title}" if ch.title else ""),
                command=lambda c=ch: self._open_chapter(c),
                anchor="w",
                height=36,
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray75", "gray25"),
            )
            btn.grid(row=row_idx + i, column=0, sticky="ew", pady=2)
        self.main_frame.grid_columnconfigure(0, weight=1)

    def _open_chapter_resume(self, chapter_id: str, page_index: int):
        ch = next((c for c in self.current_chapters if c.id == chapter_id), None)
        if ch:
            self._open_chapter(ch, page_index)

    def _open_chapter(self, chapter: ChapterInfo, initial_page: int = -1):
        if initial_page < 0:
            saved_ch_id, saved_page = get_progress(
                self.current_manga.id,
                getattr(self.current_manga, "source", "mangadex"),
            )
            initial_page = saved_page if saved_ch_id == chapter.id else 0
        self.status_label.configure(text=f"Loading chapter {chapter.chapter}...")
        threading.Thread(
            target=self._load_chapter_thread,
            args=(chapter, initial_page),
            daemon=True,
        ).start()

    def _load_chapter_thread(self, chapter: ChapterInfo, initial_page: int = 0):
        try:
            api = self.nhentai if self.current_manga and getattr(self.current_manga, "source", "") == "nhentai" else self.mangadex
            urls = api.get_chapter_images(chapter.id)
            if not urls:
                self.after(0, lambda: messagebox.showwarning("No pages", "Could not load chapter pages."))
                self.after(0, lambda: self.status_label.configure(text=""))
                return
            manga_id = self.current_manga.id if self.current_manga else ""
            source = getattr(self.current_manga, "source", "mangadex") if self.current_manga else "mangadex"
            self.after(0, lambda: ReaderPopup(self, urls, chapter, manga_id=manga_id, source=source, initial_page=initial_page))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, lambda: self.status_label.configure(text=""))

    def _go_back(self):
        if self.view_state == "chapters":
            self.view_state = "search"
            self.back_btn.grid_remove()
            self.current_manga = None
            self._load_recommendations()


def main():
    app = MangaReaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
