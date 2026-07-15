# Focus Timer + Productivity  —  modern CustomTkinter UI
# Run:  python timer.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import time, math, sys, os, shutil, subprocess
import json
import calendar
from math import sin, cos, pi, hypot, atan2
from datetime import datetime, timedelta, date

import customtkinter as ctk

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# Mini view resize behavior
RESIZE_MARGIN = 20      # px radius around each shape corner that triggers resize
MIN_MINI_SIZE = 140
MAX_MINI_SIZE = 480
MIN_MINI_UI_SCALE = 70
MAX_MINI_UI_SCALE = 160
DEFAULT_MINI_UI_SCALE = 150

# Mini window shapes (label shown in UI -> internal key)
MINI_SHAPES = [
    ("Circle", "circle"),
    ("Rounded", "rounded_rect"),
    ("Squircle", "squircle"),
    ("Hexagon", "hexagon"),
    ("Ring", "ring"),
    ("Diamond", "diamond"),
    ("Shield", "shield"),
    ("Pod", "pod"),
]
MINI_SHAPE_KEYS = [k for _, k in MINI_SHAPES]
MINI_SHAPE_LABEL = {k: d for d, k in MINI_SHAPES}
MINI_LEGACY_SHAPES = {
    "fighter": "circle", "glove": "circle", "triangle": "hexagon",
    "capsule": "pod", "star": "diamond",
}

AUDIO_FILENAME = "alarm.wav"
SETTINGS_FILENAME = "timer_settings.json"

# ---- palette (light, dark) ----
ACCENT       = ("#2563eb", "#3b82f6")
ACCENT_HOVER = ("#1d4ed8", "#2f6ff0")
GREEN        = ("#16a34a", "#22c55e")
GREEN_HOVER  = ("#15803d", "#16a34a")
AMBER        = ("#d97706", "#f59e0b")
AMBER_HOVER  = ("#b45309", "#d97706")
RED          = ("#dc2626", "#ef4444")
RED_HOVER    = ("#b91c1c", "#dc2626")
CARD         = ("#ffffff", "#1b1f2e")
CARD_2       = ("#f1f3f9", "#232838")
MUTED        = ("#64748b", "#94a3b8")
TRACK_RING   = ("#e2e8f0", "#2a3040")
SAND         = ("#d97706", "#f59e0b")
GRAPH_LINE   = ("#ea580c", "#f97316")

# clock display styles (label shown to user -> internal key)
CLOCK_STYLE_OPTIONS = [
    ("Ring", "ring"), ("Analog", "analog"), ("Digital", "digital"),
    ("Hourglass", "hourglass"), ("Bar", "bar"), ("Minimal", "minimal"),
]
CLOCK_STYLE_KEYS = [k for _, k in CLOCK_STYLE_OPTIONS]
CLOCK_STYLE_LABEL = {k: d for d, k in CLOCK_STYLE_OPTIONS}


class TimerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ---- timer state ----
        self.timer_state = "idle"
        self.total_seconds = 0
        self.remaining_seconds = 0
        self.end_at_ms = 0
        self.stopwatch_elapsed_seconds = 0
        self.stopwatch_base_elapsed = 0
        self.stopwatch_start_ms = 0
        self.stopwatch_target_seconds = 0
        self.tick_id = None
        self.last_whole = None
        self.last_tick_ms = None
        self._ring_pct = 0.0
        self._display_sig = None
        self._display_labels_style = None

        # ---- productivity ----
        self.track_var = tk.BooleanVar(value=True)
        self.save_stats_var = tk.BooleanVar(value=True)
        self.productive_ms_today = 0
        self.current_day = self._today_key()
        self.history = {}                 # {"YYYY-MM-DD": milliseconds}

        # ---- UI state ----
        self.topmost_var = tk.BooleanVar(value=True)
        self.mode_var = tk.StringVar(value="timer")
        self.theme_var = tk.StringVar(value="dark")
        self.clock_style = tk.StringVar(value="ring")
        self.mini_win = None
        self.mini_shape = tk.StringVar(value="circle")
        self.mini_shape_display = tk.StringVar(value="Circle")
        self.mini_size = tk.IntVar(value=220)
        self.mini_ui_scale = tk.IntVar(value=DEFAULT_MINI_UI_SCALE)
        self.mini_bg_trans = "magenta"
        self.preset_minutes = [5, 15, 25, 50]
        self._initial_hms = ("0", "25", "0")
        self._settings_loaded = False

        # stats window state
        self.stats_view = tk.StringVar(value="list")
        self.selected_days = set()
        self._row_vars = {}
        self._cal_selected_key = None
        now_dt = datetime.now()
        self._stats_year = now_dt.year
        self._stats_month = now_dt.month

        # mini drag/resize internals
        self._resize_edge = None
        self._resize_active = False
        self._press_info = None

        self._load_settings()

        self.clock_display_var = tk.StringVar(
            value=CLOCK_STYLE_LABEL.get(self.clock_style.get(), "Ring"))
        self.mini_shape_display.set(MINI_SHAPE_LABEL.get(self.mini_shape.get(), "Circle"))

        ctk.set_appearance_mode("dark" if self.theme_var.get() == "dark" else "light")
        ctk.set_default_color_theme("blue")

        self.title("Focus Timer")
        self.geometry("1000x660")
        self.minsize(900, 620)
        self._set_window_icon()

        self._build_fonts()
        self._build_ui()
        self._center_window()

        self._enter_mode(initial=True)
        self._show_page("focus")

        self.bind("<Return>", self._on_enter)
        self.bind("<space>", self._on_space_toggle)
        self.bind("<Escape>", lambda e: self.on_stop() if self.timer_state != "idle" else None)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- fonts
    def _build_fonts(self):
        self.font_brand  = ctk.CTkFont("Segoe UI", 20, "bold")
        self.font_h1     = ctk.CTkFont("Segoe UI", 22, "bold")
        self.font_h2     = ctk.CTkFont("Segoe UI", 15, "bold")
        self.font_body   = ctk.CTkFont("Segoe UI", 13)
        self.font_small  = ctk.CTkFont("Segoe UI", 12)
        self.font_nav    = ctk.CTkFont("Segoe UI", 14, "bold")
        self.font_time   = ctk.CTkFont("Consolas", 48, "bold")
        self.font_time_sm= ctk.CTkFont("Consolas", 22, "bold")

    # ---------------------------------------------------------------- layout
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=(0, 18), pady=18)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self._build_focus_page()
        self._build_stats_page()
        self._build_settings_page()

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=CARD)
        bar.grid(row=0, column=0, sticky="nsew")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(6, weight=1)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 8))
        ctk.CTkLabel(brand, text="\u23F1", font=ctk.CTkFont(size=26)).pack(side="left")
        ctk.CTkLabel(brand, text="Focus", font=self.font_brand).pack(side="left", padx=(8, 0))

        self.nav_buttons = {}
        items = [("focus", "\u25B6  Focus"), ("stats", "\U0001F4CA  Daily Statistics"),
                 ("settings", "\u2699  Settings")]
        for i, (key, label) in enumerate(items, start=1):
            btn = ctk.CTkButton(
                bar, text=label, anchor="w", height=42, corner_radius=10,
                font=self.font_nav, fg_color="transparent",
                text_color=("#1e293b", "#e2e8f0"), hover_color=CARD_2,
                command=lambda k=key: self._show_page(k),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=12, pady=3)
            self.nav_buttons[key] = btn

        # bottom: today total + appearance
        self.side_today = ctk.CTkLabel(bar, text="Today  00:00:00",
                                       font=self.font_h2, text_color=ACCENT)
        self.side_today.grid(row=7, column=0, sticky="w", padx=20, pady=(0, 2))
        ctk.CTkLabel(bar, text="tracked productivity", font=self.font_small,
                     text_color=MUTED).grid(row=8, column=0, sticky="w", padx=20, pady=(0, 12))

        ctk.CTkLabel(bar, text="Appearance", font=self.font_small,
                     text_color=MUTED).grid(row=9, column=0, sticky="w", padx=20)
        self.appearance_seg = ctk.CTkSegmentedButton(
            bar, values=["Dark", "Light"], command=self._on_theme_select, font=self.font_small)
        self.appearance_seg.set("Dark" if self.theme_var.get() == "dark" else "Light")
        self.appearance_seg.grid(row=10, column=0, sticky="ew", padx=16, pady=(4, 18))

    # ---------------------------------------------------------------- focus page
    def _build_focus_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        self.pages["focus"] = page

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Focus Session", font=self.font_h1).grid(row=0, column=0, sticky="w")
        hright = ctk.CTkFrame(header, fg_color="transparent")
        hright.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(hright, text="Display", font=self.font_small,
                     text_color=MUTED).pack(side="left", padx=(0, 6))
        self.clock_menu = ctk.CTkOptionMenu(
            hright, values=[d for d, _ in CLOCK_STYLE_OPTIONS],
            command=self._on_clock_style_change, variable=self.clock_display_var,
            width=120, font=self.font_small)
        self.clock_menu.pack(side="left", padx=(0, 14))
        self.mode_seg = ctk.CTkSegmentedButton(
            hright, values=["Timer", "Stopwatch"], command=self._switch_mode,
            font=self.font_body)
        self.mode_seg.set("Timer")
        self.mode_seg.pack(side="left")

        # ring card
        card = ctk.CTkFrame(page, corner_radius=18, fg_color=CARD)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)

        ring_holder = ctk.CTkFrame(card, fg_color="transparent", height=280)
        ring_holder.grid(row=0, column=0, sticky="ew", pady=(22, 6))
        ring_holder.grid_propagate(False)
        self.ring_canvas = tk.Canvas(ring_holder, highlightthickness=0, bd=0)
        self.ring_canvas.place(relx=0.5, rely=0.5, anchor="center", relwidth=1, relheight=1)
        self.ring_canvas.bind("<Configure>", self._on_ring_canvas_configure)
        self.lbl_time = ctk.CTkLabel(ring_holder, text="00:00:00", font=self.font_time,
                                     fg_color="transparent")
        self.lbl_status = ctk.CTkLabel(ring_holder, text="Ready", font=self.font_body,
                                       text_color=MUTED, fg_color="transparent")
        self.lbl_eta = ctk.CTkLabel(ring_holder, text="", font=self.font_small,
                                    text_color=MUTED, fg_color="transparent")
        # Label positions are set on first _draw_display() for the active clock style.

        # duration inputs
        self.dur_wrap = ctk.CTkFrame(card, fg_color="transparent")
        self.dur_wrap.grid(row=1, column=0, pady=(4, 4))
        self.lbl_dur_caption = ctk.CTkLabel(self.dur_wrap, text="Duration",
                                            font=self.font_small, text_color=MUTED)
        self.lbl_dur_caption.grid(row=0, column=0, columnspan=5, pady=(0, 4))
        self.var_h = tk.StringVar(value=self._initial_hms[0])
        self.var_m = tk.StringVar(value=self._initial_hms[1])
        self.var_s = tk.StringVar(value=self._initial_hms[2])
        self.time_entries = []
        self._add_time_field(self.dur_wrap, "H", self.var_h, 0, 99)
        ctk.CTkLabel(self.dur_wrap, text=":", font=self.font_time_sm).grid(row=1, column=1)
        self._add_time_field(self.dur_wrap, "M", self.var_m, 2, 59)
        ctk.CTkLabel(self.dur_wrap, text=":", font=self.font_time_sm).grid(row=1, column=3)
        self._add_time_field(self.dur_wrap, "S", self.var_s, 4, 59)

        # presets
        self.presets_wrap = ctk.CTkFrame(card, fg_color="transparent")
        self.presets_wrap.grid(row=2, column=0, pady=(6, 4))
        self.preset_buttons = []
        self._build_preset_buttons()

        # controls
        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.grid(row=3, column=0, pady=(10, 20))
        self.btn_start = ctk.CTkButton(controls, text="Start", width=120, height=44,
                                       corner_radius=12, font=self.font_h2,
                                       fg_color=GREEN, hover_color=GREEN_HOVER,
                                       command=self.on_start)
        self.btn_pause = ctk.CTkButton(controls, text="Pause", width=100, height=44,
                                       corner_radius=12, font=self.font_body,
                                       fg_color=AMBER, hover_color=AMBER_HOVER,
                                       command=self.on_pause)
        self.btn_resume = ctk.CTkButton(controls, text="Resume", width=100, height=44,
                                        corner_radius=12, font=self.font_body,
                                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                        command=self.on_resume)
        self.btn_stop = ctk.CTkButton(controls, text="Stop", width=100, height=44,
                                      corner_radius=12, font=self.font_body,
                                      fg_color=RED, hover_color=RED_HOVER,
                                      command=self.on_stop)
        for i, b in enumerate((self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop)):
            b.grid(row=0, column=i, padx=6)

        # message
        self.var_msg = tk.StringVar(value="")
        ctk.CTkLabel(page, textvariable=self.var_msg, font=self.font_small,
                     text_color=MUTED).grid(row=2, column=0, pady=(0, 8))

        # mini + productivity row
        row = ctk.CTkFrame(page, corner_radius=16, fg_color=CARD)
        row.grid(row=3, column=0, sticky="ew")
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text="Mini window", font=self.font_h2).grid(
            row=0, column=0, sticky="w", padx=16, pady=14)
        opts = ctk.CTkFrame(row, fg_color="transparent")
        opts.grid(row=0, column=2, sticky="e", padx=16, pady=10)
        ctk.CTkOptionMenu(opts, values=[d for d, _ in MINI_SHAPES],
                          command=self._on_mini_shape_change, variable=self.mini_shape_display,
                          width=140, font=self.font_small).pack(side="left", padx=(0, 8))
        ctk.CTkButton(opts, text="Open Mini", width=110, command=self.open_mini,
                      font=self.font_body).pack(side="left")

        self.lbl_today = ctk.CTkLabel(page, text="Today: 00:00:00",
                                      font=self.font_h2, text_color=ACCENT)
        self.lbl_today.grid(row=4, column=0, pady=(12, 4))
        ctk.CTkButton(page, text="View statistics \u2192", fg_color="transparent",
                      hover_color=CARD_2, text_color=ACCENT, font=self.font_body,
                      command=lambda: self._show_page("stats")).grid(row=5, column=0, pady=(0, 10))

    def _add_time_field(self, parent, label, var, col, mx):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=1, column=col, padx=6)
        ent = ctk.CTkEntry(wrap, textvariable=var, width=76, height=54, justify="center",
                           font=self.font_time_sm, corner_radius=12)
        ent.pack()
        ctk.CTkLabel(wrap, text=label, font=self.font_small, text_color=MUTED).pack()
        ent.bind("<KeyRelease>", lambda e, v=var: self._on_time_key(v))
        ent.bind("<FocusOut>", lambda e, v=var, m=mx: (self._clamp_var(v, 0, m), self._preview_time()))
        self.time_entries.append(ent)

    # ---------------------------------------------------------------- stats page
    def _build_stats_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)
        self.pages["stats"] = page

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Daily Statistics", font=self.font_h1).grid(row=0, column=0, sticky="w")
        hright = ctk.CTkFrame(header, fg_color="transparent")
        hright.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(hright, text="+ Add log", width=90, font=self.font_body,
                      fg_color=GREEN, hover_color=GREEN_HOVER,
                      command=self._add_day_log).pack(side="left", padx=(0, 10))
        self.stats_seg = ctk.CTkSegmentedButton(
            hright, values=["List", "Calendar", "Graph"], command=self._on_stats_view,
            font=self.font_body)
        self.stats_seg.set("List")
        self.stats_seg.pack(side="left")

        summary = ctk.CTkFrame(page, corner_radius=14, fg_color=CARD)
        summary.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        summary.grid_columnconfigure((0, 1), weight=1)
        self.stats_total_lbl = ctk.CTkLabel(summary, text="Total: 00:00:00",
                                            font=self.font_h2, text_color=ACCENT)
        self.stats_total_lbl.grid(row=0, column=0, sticky="w", padx=16, pady=12)
        self.stats_days_lbl = ctk.CTkLabel(summary, text="0 days recorded",
                                           font=self.font_body, text_color=MUTED)
        self.stats_days_lbl.grid(row=0, column=1, sticky="e", padx=16, pady=12)

        # selection toolbar (list view only)
        self.list_toolbar = ctk.CTkFrame(page, fg_color="transparent")
        self.list_toolbar.grid_columnconfigure(2, weight=1)
        self.chk_select_all = ctk.CTkCheckBox(self.list_toolbar, text="Select all",
                                              command=self._toggle_select_all, font=self.font_body)
        self.chk_select_all.grid(row=0, column=0, padx=(4, 12), pady=6)
        self.lbl_sel_count = ctk.CTkLabel(self.list_toolbar, text="", font=self.font_small,
                                          text_color=MUTED)
        self.lbl_sel_count.grid(row=0, column=1, sticky="w")
        self.btn_delete_sel = ctk.CTkButton(self.list_toolbar, text="\U0001F5D1 Delete selected",
                                            fg_color=RED, hover_color=RED_HOVER, font=self.font_body,
                                            width=150, state="disabled", command=self._delete_selected)
        self.btn_delete_sel.grid(row=0, column=3, sticky="e", padx=4)

        # list view
        self.stats_list = ctk.CTkScrollableFrame(page, fg_color=CARD, corner_radius=14,
                                                 label_text="")
        self.stats_list.grid_columnconfigure(0, weight=1)

        # calendar view
        self.cal_frame = ctk.CTkFrame(page, fg_color=CARD, corner_radius=14)
        self.cal_frame.grid_columnconfigure(0, weight=1)
        nav = ctk.CTkFrame(self.cal_frame, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        nav.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(nav, text="\u25C0", width=40, command=self._stats_prev_month,
                      font=self.font_body).grid(row=0, column=0)
        self.cal_title = ctk.CTkLabel(nav, text="", font=self.font_h2)
        self.cal_title.grid(row=0, column=1)
        right = ctk.CTkFrame(nav, fg_color="transparent")
        right.grid(row=0, column=2)
        ctk.CTkButton(right, text="Today", width=64, command=self._stats_today_month,
                      font=self.font_small, fg_color=CARD_2, hover_color=TRACK_RING,
                      text_color=("#1e293b", "#e2e8f0")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(right, text="\u25B6", width=40, command=self._stats_next_month,
                      font=self.font_body).pack(side="left")
        self.cal_grid = ctk.CTkFrame(self.cal_frame, fg_color="transparent")
        self.cal_grid.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        for c in range(7):
            self.cal_grid.grid_columnconfigure(c, weight=1, uniform="cal")
        detailrow = ctk.CTkFrame(self.cal_frame, fg_color="transparent")
        detailrow.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 4))
        detailrow.grid_columnconfigure(0, weight=1)
        self.cal_detail = ctk.CTkLabel(detailrow, text="Click a day to see details.",
                                       font=self.font_small, text_color=MUTED)
        self.cal_detail.grid(row=0, column=0, sticky="w")
        self.cal_edit_btn = ctk.CTkButton(detailrow, text="\u270E Edit", width=70,
                                          font=self.font_small, command=self._cal_edit_selected)
        self.cal_add_btn = ctk.CTkButton(detailrow, text="+ Add", width=64,
                                         font=self.font_small, fg_color=GREEN, hover_color=GREEN_HOVER,
                                         command=self._cal_add_selected)
        self.cal_del_btn = ctk.CTkButton(detailrow, text="\U0001F5D1 Delete", width=80,
                                         fg_color=RED, hover_color=RED_HOVER, font=self.font_small,
                                         command=self._cal_delete_selected)
        self.cal_month_total = ctk.CTkLabel(self.cal_frame, text="", font=self.font_h2,
                                            text_color=ACCENT)
        self.cal_month_total.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 12))

        # graph view
        self.graph_range = tk.StringVar(value="1M")
        self.graph_frame = ctk.CTkFrame(page, fg_color=CARD, corner_radius=14)
        self.graph_frame.grid_columnconfigure(0, weight=1)
        self.graph_frame.grid_rowconfigure(1, weight=1)
        ghead = ctk.CTkFrame(self.graph_frame, fg_color="transparent")
        ghead.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 2))
        ghead.grid_columnconfigure(0, weight=1)
        self.graph_info_lbl = ctk.CTkLabel(ghead, text="", font=self.font_h2, anchor="w")
        self.graph_info_lbl.grid(row=0, column=0, sticky="w")
        self.graph_sub_lbl = ctk.CTkLabel(ghead, text="", font=self.font_small,
                                          text_color=MUTED, anchor="w")
        self.graph_sub_lbl.grid(row=1, column=0, sticky="w")
        ctk.CTkOptionMenu(ghead, values=["1D", "1W", "1M", "3M", "YTD", "1Y", "All"],
                          variable=self.graph_range, width=90, font=self.font_body,
                          command=lambda _v: self._render_stats_graph()).grid(
            row=0, column=1, rowspan=2, sticky="e")
        self.graph_canvas = tk.Canvas(self.graph_frame, highlightthickness=0, bd=0)
        self.graph_canvas.grid(row=1, column=0, sticky="nsew", padx=14, pady=(4, 14))
        self._graph_points = []
        self._graph_size = None
        self.graph_canvas.bind("<Configure>", self._on_graph_configure)
        self.graph_canvas.bind("<Motion>", self._on_graph_motion)
        self.graph_canvas.bind("<Leave>", self._on_graph_leave)

    # ---------------------------------------------------------------- settings page
    def _build_settings_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        self.pages["settings"] = page

        ctk.CTkLabel(page, text="Settings", font=self.font_h1).grid(
            row=0, column=0, sticky="w", pady=(0, 10))

        # behaviour card
        card = ctk.CTkFrame(page, corner_radius=14, fg_color=CARD)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="Behaviour", font=self.font_h2).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 6))
        ctk.CTkSwitch(card, text="Always on top", variable=self.topmost_var,
                      command=self._toggle_topmost, font=self.font_body).grid(
            row=1, column=0, sticky="w", padx=16, pady=6)
        ctk.CTkSwitch(card, text="Track productivity (count time while running)",
                      variable=self.track_var, command=self._save_settings,
                      font=self.font_body).grid(row=2, column=0, sticky="w", padx=16, pady=6)
        ctk.CTkSwitch(card, text="Save to daily stats", variable=self.save_stats_var,
                      command=self._on_save_stats_toggle, font=self.font_body).grid(
            row=3, column=0, sticky="w", padx=16, pady=(6, 16))

        # presets card
        card2 = ctk.CTkFrame(page, corner_radius=14, fg_color=CARD)
        card2.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        card2.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card2, text="Quick presets (minutes)", font=self.font_h2).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 6))
        prow = ctk.CTkFrame(card2, fg_color="transparent")
        prow.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        self.preset_entry = ctk.CTkEntry(prow, width=260, font=self.font_body,
                                         placeholder_text="e.g. 5,15,25,50")
        self.preset_entry.insert(0, ",".join(str(v) for v in self.preset_minutes))
        self.preset_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(prow, text="Save presets", command=self._save_presets_from_entry,
                      font=self.font_body).pack(side="left")

        # mini card
        card3 = ctk.CTkFrame(page, corner_radius=14, fg_color=CARD)
        card3.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        card3.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card3, text="Mini window", font=self.font_h2).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(card3, text="Size", font=self.font_body).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 6))
        self.mini_size_lbl = ctk.CTkLabel(card3, text=f"{self.mini_size.get()} px",
                                          font=self.font_small, text_color=MUTED)
        self.mini_size_lbl.grid(row=1, column=2, sticky="e", padx=16)
        ctk.CTkSlider(card3, from_=MIN_MINI_SIZE, to=MAX_MINI_SIZE, variable=self.mini_size,
                      command=self._on_mini_size_change).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(0, 6))
        ctk.CTkLabel(card3, text="Controls size", font=self.font_body).grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 14))
        self.mini_ui_scale_lbl = ctk.CTkLabel(
            card3, text=f"{self.mini_ui_scale.get()}%",
            font=self.font_small, text_color=MUTED)
        self.mini_ui_scale_lbl.grid(row=2, column=2, sticky="e", padx=16)
        ctk.CTkSlider(card3, from_=MIN_MINI_UI_SCALE, to=MAX_MINI_UI_SCALE,
                      variable=self.mini_ui_scale,
                      command=self._on_mini_ui_scale_change).grid(
            row=2, column=1, sticky="ew", padx=8, pady=(0, 14))

        # clock display card
        card4 = ctk.CTkFrame(page, corner_radius=14, fg_color=CARD)
        card4.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        card4.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card4, text="Clock display", font=self.font_h2).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(card4, text="Style", font=self.font_body).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 16))
        ctk.CTkOptionMenu(card4, values=[d for d, _ in CLOCK_STYLE_OPTIONS],
                          command=self._on_clock_style_change,
                          variable=self.clock_display_var,
                          width=160, font=self.font_body).grid(
            row=1, column=1, sticky="w", padx=8, pady=(0, 16))

        ctk.CTkLabel(page, text="Tip: manage or delete tracked days from the Daily Statistics page.",
                     font=self.font_small, text_color=MUTED).grid(
            row=5, column=0, sticky="w", pady=(4, 4))
        self.lbl_data_path = ctk.CTkLabel(page, text="", font=self.font_small, text_color=MUTED)
        self.lbl_data_path.grid(row=6, column=0, sticky="w", pady=(0, 4))
        self.lbl_data_path.configure(text=f"Data saved locally: {self._settings_path()}")
        ctk.CTkLabel(page, text="Focus Timer  \u2022  built with CustomTkinter",
                     font=self.font_small, text_color=MUTED).grid(
            row=7, column=0, sticky="w", pady=(0, 10))

    # ---------------------------------------------------------------- navigation
    def _show_page(self, key):
        for k, page in self.pages.items():
            page.grid_remove()
        self.pages[key].grid()
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=ACCENT, text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color=("#1e293b", "#e2e8f0"))
        if key == "stats":
            self._refresh_stats()
        elif key == "focus":
            self.after(30, lambda: self._draw_display(force=True))

    def _switch_mode(self, value):
        target = "timer" if value == "Timer" else "stopwatch"
        if target == self.mode_var.get():
            return
        if self.timer_state != "idle":
            self.mode_seg.set("Timer" if self.mode_var.get() == "timer" else "Stopwatch")
            self._set_msg("Stop the current session before switching mode.")
            return
        self.mode_var.set(target)
        self._enter_mode()
        self._save_settings()

    def _enter_mode(self, initial=False):
        is_timer = self.mode_var.get() == "timer"
        self.mode_seg.set("Timer" if is_timer else "Stopwatch")
        if is_timer:
            self.title("Focus Timer")
            self.lbl_dur_caption.configure(text="Duration")
            self.remaining_seconds = self._calc_total_seconds()
            self.stopwatch_target_seconds = 0
            self._render(self.remaining_seconds)
            if not initial:
                self._set_msg("Timer mode selected.")
        else:
            self.title("Focus Stopwatch")
            self.lbl_dur_caption.configure(text="Target (optional)")
            self.total_seconds = 0
            self.stopwatch_elapsed_seconds = 0
            self.stopwatch_base_elapsed = 0
            self.stopwatch_start_ms = 0
            self.stopwatch_target_seconds = self._calc_total_seconds()
            self.remaining_seconds = 0
            self._render(0)
            if not initial:
                self._set_msg("Stopwatch mode selected.")
        self._set_buttons()
        self._set_inputs_enabled(True)

    # ---------------------------------------------------------------- theme
    def _on_theme_select(self, value=None):
        theme = "light" if (value or self.appearance_seg.get()) == "Light" else "dark"
        self.theme_var.set(theme)
        ctk.set_appearance_mode(theme)
        self.appearance_seg.set("Light" if theme == "light" else "Dark")
        self._invalidate_display()
        self.after(20, lambda: self._draw_display(force=True))
        if self.stats_win_open():
            self._refresh_stats()
        self._save_settings()

    def _on_clock_style_change(self, display=None):
        display = display or self.clock_display_var.get()
        key = dict(CLOCK_STYLE_OPTIONS).get(display, "ring")
        self.clock_style.set(key)
        self.clock_display_var.set(CLOCK_STYLE_LABEL.get(key, "Ring"))
        self._invalidate_display()
        self._draw_display(force=True)
        if self.mini_win and self.mini_win.winfo_exists():
            self._mini_build_controls()
            self._mini_render()
            self._mini_update_buttons()
        self._save_settings()

    def stats_win_open(self):
        return self.pages.get("stats") is not None and self.pages["stats"].winfo_ismapped()

    # ---------------------------------------------------------------- ring
    def _resolve_color(self, color):
        if isinstance(color, (list, tuple)):
            return color[0] if ctk.get_appearance_mode() == "Light" else color[1]
        return color

    def _accent_for_state(self):
        if self.timer_state == "running":
            return self._resolve_color(GREEN)
        if self.timer_state == "paused":
            return self._resolve_color(AMBER)
        return self._resolve_color(ACCENT)

    def _invalidate_display(self):
        self._display_sig = None
        self._display_labels_style = None
        self._display_canvas_size = None

    def _on_ring_canvas_configure(self, event):
        size = (event.width, event.height)
        if size[0] <= 2 or size[1] <= 2:
            return
        if getattr(self, "_display_canvas_size", None) == size:
            return
        self._display_canvas_size = size
        self._draw_display()

    def _draw_display(self, force=False):
        c = getattr(self, "ring_canvas", None)
        if c is None or not c.winfo_exists():
            return
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 2 or h <= 2:
            return
        style = self.clock_style.get()
        pct = round(max(0.0, min(1.0, self._ring_pct)), 4)
        time_txt = self.lbl_time.cget("text")
        status_txt = self.lbl_status.cget("text")
        sig = (style, pct, self.timer_state, time_txt, status_txt,
               ctk.get_appearance_mode(), w, h)
        if not force and getattr(self, "_display_sig", None) == sig:
            return
        self._display_sig = sig
        self._display_canvas_size = (w, h)

        bg = self._resolve_color(CARD)
        if c.cget("bg") != bg:
            c.configure(bg=bg)
        c.delete("all")
        accent = self._accent_for_state()
        track = self._resolve_color(TRACK_RING)
        txt = self._resolve_color(("#1e293b", "#e5e7eb"))
        muted = self._resolve_color(MUTED)
        self._position_display_labels(style)
        if style == "ring":
            self._draw_style_ring(c, w, h, pct, accent, track)
        elif style == "analog":
            self._draw_style_analog(c, w, h, pct, accent, track, txt, muted, time_txt, status_txt)
        elif style == "hourglass":
            self._draw_style_hourglass(c, w, h, pct, track, txt, muted, time_txt, status_txt)
        elif style == "bar":
            self._draw_style_bar(c, w, h, pct, accent, track)
        elif style == "digital":
            self._draw_style_digital(c, w, h, accent)
        # minimal: labels only

    def _position_display_labels(self, style):
        if getattr(self, "_display_labels_style", None) == style:
            return
        self._display_labels_style = style
        for lbl in (self.lbl_time, self.lbl_status, self.lbl_eta):
            lbl.place_forget()
        if style in ("analog", "hourglass"):
            return  # time drawn on canvas
        if style == "bar":
            self.lbl_time.place(relx=0.5, rely=0.32, anchor="center")
            self.lbl_status.place(relx=0.5, rely=0.46, anchor="center")
            self.lbl_eta.place(relx=0.5, rely=0.82, anchor="center")
        elif style == "minimal":
            self.lbl_time.place(relx=0.5, rely=0.46, anchor="center")
            self.lbl_eta.place(relx=0.5, rely=0.62, anchor="center")
        else:  # ring, digital
            self.lbl_time.place(relx=0.5, rely=0.42, anchor="center")
            self.lbl_status.place(relx=0.5, rely=0.57, anchor="center")
            self.lbl_eta.place(relx=0.5, rely=0.67, anchor="center")

    def _draw_style_ring(self, c, w, h, pct, accent, track):
        size = min(w, h) - 20
        thickness = max(10, int(size * 0.07))
        x0 = (w - size) / 2; y0 = (h - size) / 2
        x1 = x0 + size; y1 = y0 + size
        c.create_oval(x0, y0, x1, y1, outline=track, width=thickness)
        if pct > 0:
            c.create_arc(x0, y0, x1, y1, start=90, extent=-359.999 * pct,
                         style="arc", outline=accent, width=thickness)

    def _draw_style_digital(self, c, w, h, accent):
        # subtle rounded panel behind the (label-based) digits
        pw = min(w * 0.7, 360); ph = min(h * 0.5, 150)
        x0 = (w - pw) / 2; y0 = (h - ph) / 2
        panel = self._resolve_color(CARD_2)
        self._canvas_round_rect(c, x0, y0, x0 + pw, y0 + ph, 18, fill=panel, outline=accent, width=2)

    def _draw_style_bar(self, c, w, h, pct, accent, track):
        bw = w * 0.72; bh = 30
        x0 = (w - bw) / 2; y0 = h * 0.6
        self._canvas_round_rect(c, x0, y0, x0 + bw, y0 + bh, bh / 2, fill=track, outline="")
        if pct > 0:
            fw = max(bh, bw * pct)
            self._canvas_round_rect(c, x0, y0, x0 + fw, y0 + bh, bh / 2, fill=accent, outline="")

    def _draw_style_analog(self, c, w, h, pct, accent, track, txt, muted, hms, status):
        size = min(w, h) - 40
        cx = w / 2; cy = h / 2 - size * 0.10
        R = size * 0.40
        # elapsed pie wedge
        if pct > 0:
            soft = self._resolve_color(("#dbeafe", "#1e3a5f")) if self.timer_state == "idle" else accent
            c.create_arc(cx - R, cy - R, cx + R, cy + R, start=90, extent=-359.999 * pct,
                         style="pieslice", fill=soft, outline="")
        # face
        c.create_oval(cx - R, cy - R, cx + R, cy + R, outline=track, width=4)
        # ticks
        for i in range(12):
            ang = pi / 6 * i
            r_out = R * 0.96
            r_in = R * (0.80 if i % 3 == 0 else 0.88)
            c.create_line(cx + r_in * cos(ang), cy + r_in * sin(ang),
                          cx + r_out * cos(ang), cy + r_out * sin(ang),
                          fill=muted, width=2 if i % 3 == 0 else 1)
        # hand at remaining boundary
        ang = -pi / 2 + 2 * pi * pct
        c.create_line(cx, cy, cx + R * 0.82 * cos(ang), cy + R * 0.82 * sin(ang),
                      fill=accent, width=3)
        c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=accent, outline="")
        # text below
        c.create_text(cx, cy + R + 26, text=hms, fill=txt,
                      font=("Consolas", max(16, int(size * 0.11)), "bold"))
        c.create_text(cx, cy + R + 52, text=status, fill=muted,
                      font=("Segoe UI", max(9, int(size * 0.045))))

    def _draw_style_hourglass(self, c, w, h, pct, track, txt, muted, hms, status):
        size = min(w, h) - 50
        cx = w / 2; cy = h / 2 - size * 0.08
        hw = size * 0.30; hh = size * 0.38
        rf = 1 - pct  # remaining fraction (sand left in top)
        sand = self._resolve_color(SAND)
        # frame (two triangles)
        c.create_line(cx - hw, cy - hh, cx + hw, cy - hh, fill=track, width=3)
        c.create_line(cx - hw, cy + hh, cx + hw, cy + hh, fill=track, width=3)
        c.create_line(cx - hw, cy - hh, cx, cy, fill=track, width=3)
        c.create_line(cx + hw, cy - hh, cx, cy, fill=track, width=3)
        c.create_line(cx - hw, cy + hh, cx, cy, fill=track, width=3)
        c.create_line(cx + hw, cy + hh, cx, cy, fill=track, width=3)
        # top sand (shrinks toward neck): triangle from neck up
        if rf > 0.01:
            th = hh * rf
            tw = hw * rf
            c.create_polygon(cx, cy, cx - tw, cy - th, cx + tw, cy - th,
                             fill=sand, outline="")
        # bottom sand (grows): trapezoid rising from base
        if pct > 0.01:
            bw2 = hw * rf
            yl = cy + hh - hh * pct
            c.create_polygon(cx - hw, cy + hh, cx + hw, cy + hh,
                             cx + bw2, yl, cx - bw2, yl, fill=sand, outline="")
        # text below
        c.create_text(cx, cy + hh + 28, text=hms, fill=txt,
                      font=("Consolas", max(16, int(size * 0.11)), "bold"))
        c.create_text(cx, cy + hh + 54, text=status, fill=muted,
                      font=("Segoe UI", max(9, int(size * 0.045))))

    def _canvas_round_rect(self, c, x0, y0, x1, y1, r, fill="", outline="", width=1):
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return c.create_polygon(pts, smooth=True, fill=fill, outline=outline, width=width)

    # ---------------------------------------------------------------- validation / format
    def _on_time_key(self, var):
        raw = "".join(ch for ch in var.get() if ch.isdigit())[:3]
        if raw != var.get():
            var.set(raw)
        self._preview_time()

    def _clamp_var(self, var, mn, mx):
        try:
            v = int(var.get())
        except ValueError:
            v = 0
        var.set(str(max(mn, min(mx, v))))

    def _format_hms(self, s):
        s = max(0, int(s)); h = s // 3600; m = (s % 3600) // 60
        return f"{h:02d}:{m:02d}:{s % 60:02d}"

    def _calc_total_seconds(self):
        self._clamp_var(self.var_h, 0, 99)
        self._clamp_var(self.var_m, 0, 59)
        self._clamp_var(self.var_s, 0, 59)
        try:
            h = int(self.var_h.get() or "0"); m = int(self.var_m.get() or "0"); s = int(self.var_s.get() or "0")
        except ValueError:
            return 0
        return h * 3600 + m * 60 + s

    def _current_elapsed_seconds(self):
        if self.timer_state == "running":
            return self.stopwatch_base_elapsed + max(0, math.floor((self._now_ms() - self.stopwatch_start_ms) / 1000))
        return self.stopwatch_base_elapsed

    # ---------------------------------------------------------------- timer controls
    def on_start(self):
        if self.timer_state != "idle":
            return
        if self.mode_var.get() == "timer":
            self.total_seconds = self._calc_total_seconds()
            if self.total_seconds <= 0:
                messagebox.showwarning("Invalid time", "Please enter a time greater than 0 seconds.")
                return
            self.remaining_seconds = self.total_seconds
            self.end_at_ms = self._now_ms() + self.remaining_seconds * 1000
        else:
            self.total_seconds = 0
            self.stopwatch_base_elapsed = 0
            self.stopwatch_start_ms = self._now_ms()
            self.stopwatch_elapsed_seconds = 0
            self.stopwatch_target_seconds = self._calc_total_seconds()
            self.remaining_seconds = 0
        self.last_tick_ms = self._now_ms()
        self.timer_state = "running"
        self._set_buttons(); self._set_inputs_enabled(False)
        self._update_eta_label()
        self._set_msg("Started."); self._tick()

    def on_pause(self):
        if self.timer_state != "running":
            return
        self._apply_productivity_delta()
        if self.mode_var.get() == "timer":
            self.remaining_seconds = max(0, math.ceil((self.end_at_ms - self._now_ms()) / 1000))
        else:
            self.stopwatch_base_elapsed = self._current_elapsed_seconds()
            self.stopwatch_elapsed_seconds = self.stopwatch_base_elapsed
            self.remaining_seconds = self.stopwatch_elapsed_seconds
        self._cancel_tick(); self.timer_state = "paused"
        self._set_buttons(); self._set_msg("Paused."); self._update_eta_label()
        self._render(self.remaining_seconds)

    def on_resume(self):
        if self.timer_state != "paused":
            return
        if self.mode_var.get() == "timer":
            if self.remaining_seconds <= 0:
                return
            self.end_at_ms = self._now_ms() + self.remaining_seconds * 1000
        else:
            self.stopwatch_start_ms = self._now_ms()
            self.remaining_seconds = self.stopwatch_base_elapsed
        self.last_tick_ms = self._now_ms()
        self.timer_state = "running"
        self._set_buttons(); self._set_msg("Resumed."); self._tick(); self._update_eta_label()

    def on_stop(self):
        self._apply_productivity_delta()
        self._cancel_tick(); self.timer_state = "idle"
        self.stopwatch_elapsed_seconds = 0
        self.stopwatch_base_elapsed = 0
        self.stopwatch_start_ms = 0
        self.stopwatch_target_seconds = self._calc_total_seconds() if self.mode_var.get() == "stopwatch" else 0
        self.total_seconds = 0; self.remaining_seconds = 0
        self._render(0); self._set_buttons(); self._set_inputs_enabled(True); self._set_msg("Stopped.")
        self._update_eta_label()
        self._save_settings()

    def _on_save_stats_toggle(self):
        if self.save_stats_var.get():
            self._set_msg("Saving tracked time to daily stats.")
        else:
            self._set_msg("Paused saving to daily stats (time won't be recorded).")
        self._save_settings()

    # ---------------------------------------------------------------- tick / productivity
    def _tick(self):
        now = self._now_ms()
        if self._today_key() != self.current_day:
            self.current_day = self._today_key()
            self.productive_ms_today = self.history.get(self.current_day, 0)
            self._update_today_label()

        if self.mode_var.get() == "timer":
            left = max(0, math.ceil((self.end_at_ms - now) / 1000))
            self.remaining_seconds = left
            self._render(left)
        else:
            self.stopwatch_elapsed_seconds = self._current_elapsed_seconds()
            self.remaining_seconds = self.stopwatch_elapsed_seconds
            self._render(self.stopwatch_elapsed_seconds)
            left = None

        if self.timer_state == "running" and self.track_var.get() and self.last_tick_ms is not None:
            self._add_productivity(max(0, now - self.last_tick_ms))
        self.last_tick_ms = now

        if self.mode_var.get() == "timer" and left <= 0:
            self.timer_state = "idle"; self._set_buttons(); self._set_inputs_enabled(True)
            self._set_msg("Time's up!"); self._update_eta_label(); self._play_alarm()
            self._save_settings()
            return
        if self.mode_var.get() == "stopwatch" and self.stopwatch_target_seconds > 0 \
                and self.stopwatch_elapsed_seconds >= self.stopwatch_target_seconds:
            self.timer_state = "idle"; self._set_buttons(); self._set_inputs_enabled(True)
            self._set_msg("Stopwatch complete!"); self._update_eta_label(); self._play_alarm()
            self._save_settings()
            return
        self.tick_id = self.after(100, self._tick)

    def _apply_productivity_delta(self):
        if self.timer_state == "running" and self.track_var.get() and self.last_tick_ms is not None:
            now = self._now_ms()
            self._add_productivity(max(0, now - self.last_tick_ms))
            self.last_tick_ms = now

    def _add_productivity(self, delta_ms):
        self.productive_ms_today += delta_ms
        if self.save_stats_var.get():
            today = self._today_key()
            self.history[today] = self.history.get(today, 0) + delta_ms
        self._update_today_label()

    # ---------------------------------------------------------------- render helpers
    def _render(self, seconds_left):
        if seconds_left != self.last_whole:
            self.lbl_time.configure(text=self._format_hms(seconds_left))
            self.last_whole = seconds_left
        if self.mode_var.get() == "timer":
            self._ring_pct = 0.0 if self.total_seconds <= 0 else (1 - seconds_left / self.total_seconds)
        else:
            if self.stopwatch_target_seconds > 0:
                self._ring_pct = min(1.0, self.stopwatch_elapsed_seconds / self.stopwatch_target_seconds)
            else:
                self._ring_pct = 0.0
        status = {"idle": "Ready", "running": "Running", "paused": "Paused"}[self.timer_state]
        if self.timer_state == "idle" and self.last_whole and seconds_left == 0:
            status = "Ready"
        if self.lbl_status.cget("text") != status:
            self.lbl_status.configure(text=status)
        self._draw_display()
        if self.mini_win and self.mini_win.winfo_exists():
            self._mini_render()
        self._update_eta_label()

    def _set_buttons(self):
        states = {
            "idle":   ("normal", "disabled", "disabled", "disabled"),
            "running": ("disabled", "normal", "disabled", "normal"),
            "paused": ("disabled", "disabled", "normal", "normal"),
        }[self.timer_state]
        for btn, st in zip((self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop), states):
            btn.configure(state=st)
        try:
            self.mode_seg.configure(state="disabled" if self.timer_state != "idle" else "normal")
        except Exception:
            pass
        if self.mini_win and self.mini_win.winfo_exists():
            self._mini_update_buttons()

    def _set_inputs_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for ent in getattr(self, "time_entries", []):
            try:
                ent.configure(state=state)
            except Exception:
                pass
        for btn in getattr(self, "preset_buttons", []):
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _set_msg(self, text):
        self.var_msg.set(text or "")

    def _update_today_label(self):
        s = round(self.productive_ms_today / 1000)
        txt = f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
        self.lbl_today.configure(text=f"Today: {txt}")
        self.side_today.configure(text=f"Today  {txt}")

    def _today_key(self):
        return datetime.now().strftime("%Y-%m-%d")

    def _update_eta_label(self):
        if self.mode_var.get() == "stopwatch":
            if self.stopwatch_target_seconds > 0:
                self.lbl_eta.configure(
                    text=f"Target {self._format_hms(self.stopwatch_target_seconds)}")
            else:
                self.lbl_eta.configure(text="Counting up")
        elif self.timer_state == "running":
            end_dt = datetime.fromtimestamp(self.end_at_ms / 1000)
            self.lbl_eta.configure(text=f"Ends at {end_dt.strftime('%H:%M')}")
        elif self.timer_state == "paused" and self.remaining_seconds > 0:
            self.lbl_eta.configure(text="Paused")
        else:
            self.lbl_eta.configure(text="")

    def _on_enter(self, _e=None):
        w = self.focus_get()
        if isinstance(w, (ctk.CTkEntry, tk.Entry)):
            self._preview_time()
            return
        if self.timer_state == "idle":
            self.on_start()

    def _on_space_toggle(self, _event=None):
        w = self.focus_get()
        if isinstance(w, (ctk.CTkEntry, tk.Entry)):
            return
        if self.timer_state == "idle":
            self.on_start()
        elif self.timer_state == "running":
            self.on_pause()
        elif self.timer_state == "paused":
            self.on_resume()
        return "break"

    def _preview_time(self):
        if self.timer_state != "idle":
            return
        if self.mode_var.get() == "timer":
            self.total_seconds = self._calc_total_seconds()
            self._render(self.total_seconds)
        else:
            self.stopwatch_target_seconds = self._calc_total_seconds()
            self._render(0)

    # ---------------------------------------------------------------- presets
    def _apply_preset(self, minutes):
        if self.timer_state != "idle":
            return
        self.var_h.set("0"); self.var_m.set(str(minutes)); self.var_s.set("0")
        self._preview_time()
        self._set_msg(f"Preset applied: {minutes} minutes.")
        self._save_settings()

    def _sanitize_preset_minutes(self, values):
        cleaned = []
        for v in values:
            try:
                iv = int(v)
            except Exception:
                continue
            if 1 <= iv <= 999 and iv not in cleaned:
                cleaned.append(iv)
        return cleaned[:6]

    def _build_preset_buttons(self):
        for btn in getattr(self, "preset_buttons", []):
            try:
                btn.destroy()
            except Exception:
                pass
        self.preset_buttons = []
        for mins in self.preset_minutes:
            btn = ctk.CTkButton(self.presets_wrap, text=f"{mins}m", width=58, height=32,
                                corner_radius=16, font=self.font_small,
                                fg_color=CARD_2, hover_color=TRACK_RING,
                                text_color=("#1e293b", "#e2e8f0"),
                                command=lambda m=mins: self._apply_preset(m))
            btn.pack(side="left", padx=4)
            self.preset_buttons.append(btn)
        edit = ctk.CTkButton(self.presets_wrap, text="Edit", width=58, height=32,
                             corner_radius=16, font=self.font_small,
                             fg_color="transparent", hover_color=CARD_2,
                             text_color=ACCENT, command=self._customize_presets)
        edit.pack(side="left", padx=4)
        self.preset_buttons.append(edit)

    def _customize_presets(self):
        if self.timer_state != "idle":
            self._set_msg("Stop the current session before editing presets.")
            return
        current = ",".join(str(v) for v in self.preset_minutes)
        raw = simpledialog.askstring("Customize Presets",
                                     "Enter preset minutes separated by commas (1-999).\nExample: 5,15,25,50",
                                     initialvalue=current, parent=self)
        if raw is None:
            return
        self._commit_presets(raw)

    def _save_presets_from_entry(self):
        self._commit_presets(self.preset_entry.get())

    def _commit_presets(self, raw):
        values = [p.strip() for p in raw.split(",") if p.strip()]
        new_values = self._sanitize_preset_minutes(values)
        if not new_values:
            messagebox.showwarning("Invalid presets", "Please enter at least one valid minute value.")
            return
        self.preset_minutes = new_values
        self._build_preset_buttons()
        if hasattr(self, "preset_entry"):
            self.preset_entry.delete(0, "end")
            self.preset_entry.insert(0, ",".join(str(v) for v in self.preset_minutes))
        self._set_inputs_enabled(self.timer_state == "idle")
        self._set_msg("Quick presets updated.")
        self._save_settings()

    def _toggle_topmost(self):
        self.attributes("-topmost", self.topmost_var.get())
        if self.mini_win and self.mini_win.winfo_exists():
            self.mini_win.attributes("-topmost", self.topmost_var.get())
        self._save_settings()

    def _on_mini_size_change(self, value):
        size = int(float(value))
        self.mini_size_lbl.configure(text=f"{size} px")
        if self.mini_win and self.mini_win.winfo_exists():
            self.mini_win.geometry(f"{size}x{size}+{self.mini_win.winfo_x()}+{self.mini_win.winfo_y()}")
            self.mini_canvas.config(width=size, height=size)
            self._refresh_mini_window()
        self._save_settings()

    def _on_mini_ui_scale_change(self, value):
        pct = int(float(value))
        self.mini_ui_scale_lbl.configure(text=f"{pct}%")
        self._refresh_mini_window()
        self._save_settings()

    def _mini_ui_factor(self):
        pct = max(MIN_MINI_UI_SCALE, min(MAX_MINI_UI_SCALE, int(self.mini_ui_scale.get())))
        return pct / 100.0

    def _mini_time_font(self, size):
        ui = self._mini_ui_factor()
        return ("Consolas", max(10, min(20, int(size * 0.160 * ui))), "bold")

    def _refresh_mini_window(self):
        if not (self.mini_win and self.mini_win.winfo_exists()):
            return
        self._mini_draw_shape()
        self._mini_build_controls()
        self._mini_render()
        self._mini_update_buttons()
        self._install_resize_handlers()

    def _on_mini_shape_change(self, display=None):
        display = display or self.mini_shape_display.get()
        key = dict(MINI_SHAPES).get(display, "circle")
        self.mini_shape.set(key)
        self.mini_shape_display.set(MINI_SHAPE_LABEL.get(key, "Circle"))
        if self.mini_win and self.mini_win.winfo_exists():
            self._refresh_mini_window()
        self._save_settings()

    def _sanitize_mini_shape(self, value):
        key = str(value or "circle")
        key = MINI_LEGACY_SHAPES.get(key, key)
        return key if key in MINI_SHAPE_KEYS else "circle"

    def _mini_layout(self, size):
        """Compute control positions/sizes so buttons fit inside each shape."""
        ui = self._mini_ui_factor()
        shape = self.mini_shape.get()
        cx = cy = size / 2.0
        inset = max(6, size * 0.045)
        R = size / 2.0 - inset

        if shape == "ring":
            inner_r = R * 0.56
            time_y = cy - inner_r * 0.12
            btn_y = cy + inner_r * 0.42
            dy = btn_y - cy
            half_w = inner_r * 0.82
        elif shape == "diamond":
            time_y = cy - size * 0.10
            btn_y = cy + size * 0.14
            dy = btn_y - cy
            half_w = max(size * 0.14, (R - abs(dy)) * 0.78)
        elif shape == "shield":
            time_y = cy - size * 0.08
            btn_y = cy + size * 0.16
            half_w = R * 0.62
        elif shape == "hexagon":
            time_y = cy - size * 0.12
            btn_y = cy + size * 0.10
            dy = btn_y - cy
            half_w = math.sqrt(max(1, R * R - dy * dy)) * 0.78
        elif shape == "pod":
            time_y = cy - size * 0.14
            btn_y = cy + size * 0.10
            half_w = R * 0.68
        else:  # circle, rounded_rect, squircle
            time_y = cy - size * 0.14
            btn_y = cy + size * 0.08
            dy = btn_y - cy
            half_w = math.sqrt(max(1, R * R - dy * dy)) * 0.80

        btn_span = min(size * 0.88, 2 * half_w * 0.92)
        btn_gap = max(2, int(size * 0.008 * ui))
        use_2x2 = btn_span < 132 or size < 185
        if use_2x2:
            btn_row_h = max(20, int(size * 0.105 * ui))
            btn_frame_h = btn_row_h * 2 + btn_gap
            btn_y = cy + size * 0.04
        else:
            btn_row_h = max(22, int(size * 0.098 * ui))
            btn_frame_h = btn_row_h
            btn_y = cy + size * 0.06

        cols = 2 if use_2x2 else 4
        slot_w = max(18, (btn_span - btn_gap * (cols + 1)) // cols)
        btn_font = max(8, min(14, int(slot_w * 0.44 * ui)))
        ipadx = max(1, int((slot_w - btn_font * 3.6) // 2 * ui))
        ipady = max(2, int(size * 0.014 * ui))

        close_inset = inset + max(6, size * 0.035)
        close_x = size - close_inset
        close_y = close_inset

        return {
            "cx": cx, "cy": cy, "R": R, "inset": inset,
            "time_y": time_y, "btn_y": btn_y, "btn_span": btn_span,
            "btn_gap": btn_gap, "btn_font": btn_font, "btn_row_h": btn_row_h,
            "btn_frame_h": btn_frame_h, "ipadx": ipadx, "ipady": ipady,
            "use_2x2": use_2x2, "cols": cols,
            "close_x": close_x, "close_y": close_y,
            "clock_cy": size * 0.30,
        }

    # ---------------------------------------------------------------- statistics
    def _on_stats_view(self, value):
        self.stats_view.set({"Calendar": "calendar", "Graph": "graph"}.get(value, "list"))
        self._refresh_stats()

    def _total_history_ms(self):
        return sum(int(v) for v in self.history.values())

    def _format_compact_ms(self, ms):
        s = round(int(ms) / 1000)
        if s <= 0:
            return ""
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        if h:
            return f"{h}h {m:02d}m"
        if m:
            return f"{m}m"
        return f"{sec}s"

    def _refresh_stats(self):
        if "stats" not in self.pages:
            return
        total = self._total_history_ms()
        days = len([1 for v in self.history.values() if int(v) > 0])
        self.stats_total_lbl.configure(text=f"Total: {self._format_hms(round(total / 1000))}")
        self.stats_days_lbl.configure(text=f"{days} day(s) recorded")
        self.stats_list.grid_remove()
        self.cal_frame.grid_remove()
        self.list_toolbar.grid_remove()
        self.graph_frame.grid_remove()
        if self.stats_view.get() == "calendar":
            self.cal_frame.grid(row=3, column=0, sticky="nsew")
            self._render_stats_calendar()
        elif self.stats_view.get() == "graph":
            self.graph_frame.grid(row=3, column=0, sticky="nsew")
            self._render_stats_graph()
        else:
            self.list_toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
            self.stats_list.grid(row=3, column=0, sticky="nsew")
            self._render_stats_list()

    # ---------------------------------------------------------------- stats graph
    def _graph_hover_fmt(self, ms):
        return self._format_compact_ms(ms) or "0m"

    def _graph_series(self):
        """Daily (date, ms) series over the selected range, zero-filled."""
        rows = [(d, int(ms)) for d, ms in self.history.items()
                if int(ms) > 0 and self._is_valid_date_key(d)]
        if not rows:
            return []
        today = date.today()
        rng = self.graph_range.get()
        if rng == "1D":
            start = today - timedelta(days=1)
        elif rng == "1W":
            start = today - timedelta(days=6)
        elif rng == "1M":
            start = today - timedelta(days=29)
        elif rng == "3M":
            start = today - timedelta(days=89)
        elif rng == "YTD":
            start = date(today.year, 1, 1)
        elif rng == "1Y":
            start = today - timedelta(days=364)
        else:  # All
            earliest = min(datetime.strptime(d, "%Y-%m-%d").date() for d, _ in rows)
            start = min(earliest, today - timedelta(days=6))
        by_day = dict(rows)
        series = []
        day = start
        while day <= today:
            series.append((day, by_day.get(day.strftime("%Y-%m-%d"), 0)))
            day += timedelta(days=1)
        return series

    def _set_graph_header(self, main, sub):
        self.graph_info_lbl.configure(text=main)
        self.graph_sub_lbl.configure(text=sub)

    def _render_stats_graph(self):
        self._graph_series_data = self._graph_series()
        total = sum(ms for _, ms in self._graph_series_data)
        desc = {"1D": "Last day", "1W": "Last 7 days", "1M": "Last 30 days",
                "3M": "Last 3 months", "YTD": "This year", "1Y": "Last year",
                "All": "All time"}.get(self.graph_range.get(), "")
        if self._graph_series_data:
            self._graph_default_header = (f"Total: {self._graph_hover_fmt(total)}", desc)
        else:
            self._graph_default_header = ("No data yet", "Track time to see your graph here.")
        self._set_graph_header(*self._graph_default_header)
        self._draw_graph()

    def _draw_graph(self):
        c = self.graph_canvas
        if not c.winfo_exists():
            return
        c.delete("all")
        self._graph_points = []
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 2 or h <= 2:
            return
        c.configure(bg=self._resolve_color(CARD))
        series = getattr(self, "_graph_series_data", [])
        muted = self._resolve_color(MUTED)
        if not series or all(ms == 0 for _, ms in series):
            c.create_text(w / 2, h / 2, text="No tracked time in this range.",
                          fill=muted, font=("Segoe UI", 12))
            return
        line = self._resolve_color(GRAPH_LINE)
        grid = self._resolve_color(TRACK_RING)
        ml, mr, mt, mb = 10, 10, 34, 26
        pw = w - ml - mr
        ph = h - mt - mb
        max_ms = max(ms for _, ms in series) or 1
        n = len(series)

        for frac in (0.5, 1.0):
            y = mt + ph * (1 - frac)
            c.create_line(ml, y, w - mr, y, fill=grid, width=1)
            c.create_text(ml + 2, y - 8, text=self._graph_hover_fmt(max_ms * frac),
                          fill=muted, anchor="w", font=("Segoe UI", 8))
        c.create_line(ml, mt + ph, w - mr, mt + ph, fill=grid, width=1)

        pts = []
        for i, (day, ms) in enumerate(series):
            x = ml + (pw * i / (n - 1) if n > 1 else pw / 2)
            y = mt + ph * (1 - ms / max_ms)
            pts.append((x, y, day, ms))
        self._graph_points = pts

        if len(pts) >= 2:
            flat = []
            for x, y, _, _ in pts:
                flat += [x, y]
            c.create_line(*flat, fill=line, width=2, joinstyle="round", capstyle="round")
        else:
            x, y, _, _ = pts[0]
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill=line, outline="")

        span_days = (series[-1][0] - series[0][0]).days
        fmt = "%b %Y" if span_days > 200 else "%d %b"
        n_lbl = min(6, n)
        idxs = [round(i * (n - 1) / (n_lbl - 1)) for i in range(n_lbl)] if n_lbl >= 2 else [0]
        for i in idxs:
            x, _, day, _ = pts[i]
            c.create_text(x, h - mb / 2, text=day.strftime(fmt),
                          fill=muted, font=("Segoe UI", 8))

    def _on_graph_configure(self, event):
        size = (event.width, event.height)
        if size[0] <= 2 or size[1] <= 2 or self._graph_size == size:
            return
        self._graph_size = size
        self._draw_graph()

    def _on_graph_motion(self, e):
        pts = self._graph_points
        if not pts:
            return
        c = self.graph_canvas
        c.delete("ghover")
        x, y, day, ms = min(pts, key=lambda p: abs(p[0] - e.x))
        w = c.winfo_width()
        h = c.winfo_height()
        accent = self._resolve_color(GRAPH_LINE)
        c.create_line(x, 26, x, h - 26, fill=self._resolve_color(MUTED),
                      width=1, tags="ghover")
        c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=accent, outline="", tags="ghover")
        label = f"{day.strftime('%d %b')}  \u00B7  {self._graph_hover_fmt(ms)}"
        tx = min(max(x, 60), w - 60)
        c.create_text(tx, 12, text=label, fill=self._resolve_color(("#1e293b", "#e5e7eb")),
                      font=("Segoe UI", 9, "bold"), tags="ghover")
        self._set_graph_header(self._graph_hover_fmt(ms), day.strftime("%A, %d %B %Y"))

    def _on_graph_leave(self, _e=None):
        self.graph_canvas.delete("ghover")
        if hasattr(self, "_graph_default_header"):
            self._set_graph_header(*self._graph_default_header)

    def _render_stats_list(self):
        for child in self.stats_list.winfo_children():
            child.destroy()
        rows = [(d, int(ms)) for d, ms in self.history.items() if int(ms) > 0]
        rows.sort(reverse=True)
        self._row_vars = {}
        # drop selections for days that no longer exist
        self.selected_days &= {d for d, _ in rows}
        if not rows:
            ctk.CTkLabel(self.stats_list, text="No tracked time yet.\nUse + Add log to record time for any date.",
                         font=self.font_body, text_color=MUTED).grid(row=0, column=0, pady=40)
            self._update_selection_ui()
            return
        for i, (day, ms) in enumerate(rows):
            try:
                dt = datetime.strptime(day, "%Y-%m-%d")
                weekday = dt.strftime("%a")
                pretty = dt.strftime("%d %b %Y")
            except Exception:
                weekday, pretty = "", day
            rowf = ctk.CTkFrame(self.stats_list, fg_color=CARD_2, corner_radius=10)
            rowf.grid(row=i, column=0, sticky="ew", padx=6, pady=4)
            rowf.grid_columnconfigure(2, weight=1)
            var = tk.BooleanVar(value=day in self.selected_days)
            self._row_vars[day] = var
            ctk.CTkCheckBox(rowf, text="", width=24, variable=var,
                            command=lambda d=day: self._on_row_toggle(d)).grid(
                row=0, column=0, padx=(12, 4), pady=10)
            ctk.CTkLabel(rowf, text=weekday, width=40, font=self.font_h2,
                         text_color=ACCENT).grid(row=0, column=1, padx=(2, 8))
            ctk.CTkLabel(rowf, text=pretty, font=self.font_body, anchor="w").grid(
                row=0, column=2, sticky="w")
            ctk.CTkLabel(rowf, text=self._format_hms(round(ms / 1000)),
                         font=self.font_time_sm).grid(row=0, column=3, padx=(8, 8))
            ctk.CTkButton(rowf, text="\u270E", width=36, font=self.font_body,
                          fg_color="transparent", hover_color=TRACK_RING,
                          text_color=ACCENT, command=lambda d=day: self._edit_day(d)).grid(
                row=0, column=4, padx=2)
            ctk.CTkButton(rowf, text="\U0001F5D1", width=36, font=self.font_body,
                          fg_color="transparent", hover_color=TRACK_RING,
                          text_color=RED, command=lambda d=day: self._delete_days([d])).grid(
                row=0, column=5, padx=(2, 10))
        self._update_selection_ui()

    def _on_row_toggle(self, day):
        var = self._row_vars.get(day)
        if var is None:
            return
        if var.get():
            self.selected_days.add(day)
        else:
            self.selected_days.discard(day)
        self._update_selection_ui()

    def _toggle_select_all(self):
        select = bool(self.chk_select_all.get())
        for day, var in self._row_vars.items():
            var.set(select)
            if select:
                self.selected_days.add(day)
            else:
                self.selected_days.discard(day)
        self._update_selection_ui()

    def _update_selection_ui(self):
        n = len(self.selected_days)
        self.lbl_sel_count.configure(text=f"{n} selected" if n else "")
        try:
            self.btn_delete_sel.configure(state="normal" if n else "disabled")
        except Exception:
            pass
        total = len(self._row_vars)
        try:
            if total and n == total:
                self.chk_select_all.select()
            else:
                self.chk_select_all.deselect()
        except Exception:
            pass

    def _delete_selected(self):
        if self.selected_days:
            self._delete_days(list(self.selected_days))

    def _delete_days(self, keys):
        keys = [k for k in keys if k in self.history]
        if not keys:
            return
        if len(keys) == 1:
            msg = f"Delete tracked time for {keys[0]}?"
        else:
            msg = f"Delete tracked time for {len(keys)} selected day(s)?"
        if not messagebox.askyesno("Delete statistics", msg + "\nThis cannot be undone."):
            return
        today = self._today_key()
        for k in keys:
            self.history.pop(k, None)
            self.selected_days.discard(k)
            if k == today:
                self.productive_ms_today = 0
        self._update_today_label()
        self._refresh_stats()
        self._set_msg(f"Deleted {len(keys)} day(s) from statistics.")
        self._save_settings()

    def _edit_day(self, day):
        current = int(self.history.get(day, 0))
        try:
            pretty = datetime.strptime(day, "%Y-%m-%d").strftime("%A, %d %b %Y")
        except Exception:
            pretty = day
        self._open_time_dialog(day, pretty, round(current / 1000), mode="set")

    def _add_day_log(self, day_key=None):
        day_key = day_key or self._cal_selected_key or self._today_key()
        self._open_time_dialog(day_key, "Add tracked time", 0, mode="add", allow_date_edit=True)

    def _apply_day_time(self, day_key, total_seconds, mode="set"):
        today = self._today_key()
        if mode == "add" and total_seconds > 0:
            self.history[day_key] = int(self.history.get(day_key, 0)) + total_seconds * 1000
        elif total_seconds <= 0:
            if mode == "set":
                self.history.pop(day_key, None)
                if day_key == today:
                    self.productive_ms_today = 0
                self._update_today_label()
                self._refresh_stats()
                self._save_settings()
            return mode == "set"
        else:
            self.history[day_key] = total_seconds * 1000
        if day_key == today:
            self.productive_ms_today = int(self.history.get(day_key, 0))
        self._update_today_label()
        self._refresh_stats()
        self._save_settings()
        return True

    def _open_time_dialog(self, day_key, pretty, initial_seconds, mode="set", allow_date_edit=False):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Add time log" if mode == "add" else "Edit tracked time")
        dlg.geometry("360x300" if allow_date_edit else "340x230")
        dlg.resizable(False, False)
        dlg.transient(self)
        try:
            dlg.after(80, dlg.grab_set)
        except Exception:
            pass
        title = "Add tracked time" if mode == "add" else pretty
        ctk.CTkLabel(dlg, text=title, font=self.font_h2).pack(pady=(16, 2))
        hint = ("Pick a date and enter time to add to that day."
                if mode == "add" else "Adjust the tracked time for this day")
        ctk.CTkLabel(dlg, text=hint, font=self.font_small, text_color=MUTED).pack(pady=(0, 10))

        vdate = tk.StringVar(value=day_key)
        if allow_date_edit:
            drow = ctk.CTkFrame(dlg, fg_color="transparent")
            drow.pack(pady=(0, 8))
            ctk.CTkLabel(drow, text="Date", font=self.font_small, text_color=MUTED).pack(side="left", padx=(0, 8))
            ctk.CTkEntry(drow, textvariable=vdate, width=140, font=self.font_body,
                         placeholder_text="YYYY-MM-DD").pack(side="left")

        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack()
        h0 = initial_seconds // 3600
        m0 = (initial_seconds % 3600) // 60
        s0 = initial_seconds % 60
        vh = tk.StringVar(value=str(h0)); vm = tk.StringVar(value=str(m0)); vs = tk.StringVar(value=str(s0))
        for i, (lbl, var) in enumerate((("H", vh), ("M", vm), ("S", vs))):
            wrap = ctk.CTkFrame(row, fg_color="transparent")
            wrap.grid(row=0, column=i, padx=6)
            ctk.CTkEntry(wrap, textvariable=var, width=64, height=44, justify="center",
                         font=self.font_time_sm).pack()
            ctk.CTkLabel(wrap, text=lbl, font=self.font_small, text_color=MUTED).pack()

        def save():
            def iv(v):
                try:
                    return max(0, int(v.get() or "0"))
                except Exception:
                    return 0
            date_key = vdate.get().strip()
            if not self._is_valid_date_key(date_key):
                messagebox.showwarning("Invalid date", "Please enter a date as YYYY-MM-DD.")
                return
            total = iv(vh) * 3600 + min(59, iv(vm)) * 60 + min(59, iv(vs))
            if mode == "add" and total <= 0:
                messagebox.showwarning("Invalid time", "Please enter a time greater than 0.")
                return
            if self._apply_day_time(date_key, total, mode=mode):
                if mode == "add":
                    self._set_msg(f"Added {self._format_hms(total)} to {date_key}.")
                else:
                    self._set_msg(f"Updated tracked time for {date_key}.")
            dlg.destroy()

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(pady=(16, 8))
        ctk.CTkButton(btns, text="Cancel", width=100, fg_color=CARD_2, hover_color=TRACK_RING,
                      text_color=("#1e293b", "#e2e8f0"), command=dlg.destroy).pack(side="left", padx=6)
        save_label = "Add" if mode == "add" else "Save"
        ctk.CTkButton(btns, text=save_label, width=100, fg_color=GREEN, hover_color=GREEN_HOVER,
                      command=save).pack(side="left", padx=6)

    def _stats_prev_month(self):
        self._stats_month -= 1
        if self._stats_month < 1:
            self._stats_month = 12; self._stats_year -= 1
        self._render_stats_calendar()

    def _stats_next_month(self):
        self._stats_month += 1
        if self._stats_month > 12:
            self._stats_month = 1; self._stats_year += 1
        self._render_stats_calendar()

    def _stats_today_month(self):
        now_dt = datetime.now()
        self._stats_year, self._stats_month = now_dt.year, now_dt.month
        self._render_stats_calendar()

    def _render_stats_calendar(self):
        for child in self.cal_grid.winfo_children():
            child.destroy()
        self._cal_selected_key = None
        self.cal_detail.configure(text="Click a day to see details.")
        try:
            self.cal_edit_btn.grid_remove()
            self.cal_add_btn.grid_remove()
            self.cal_del_btn.grid_remove()
        except Exception:
            pass
        self.cal_title.configure(text=f"{calendar.month_name[self._stats_month]} {self._stats_year}")
        for col, name in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            ctk.CTkLabel(self.cal_grid, text=name, font=self.font_small,
                         text_color=MUTED).grid(row=0, column=col, pady=(0, 4))
        today_key = self._today_key()
        month_total = 0
        cal = calendar.Calendar(firstweekday=6)
        weeks = cal.monthdayscalendar(self._stats_year, self._stats_month)
        for r, week in enumerate(weeks, start=1):
            for col, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(self.cal_grid, text="").grid(row=r, column=col, padx=2, pady=2)
                    continue
                key = f"{self._stats_year:04d}-{self._stats_month:02d}-{day:02d}"
                ms = int(self.history.get(key, 0))
                month_total += ms
                has = ms > 0
                label = f"{day}\n{self._format_compact_ms(ms)}" if has else f"{day}\n"
                cell = ctk.CTkButton(
                    self.cal_grid, text=label, width=58, height=48, corner_radius=10,
                    font=self.font_small,
                    fg_color=ACCENT if has else CARD_2,
                    hover_color=ACCENT_HOVER if has else TRACK_RING,
                    text_color="#ffffff" if has else ("#1e293b", "#e2e8f0"),
                    border_width=2 if key == today_key else 0,
                    border_color=AMBER,
                    command=lambda k=key, m=ms: self._on_calendar_day_click(k, m),
                )
                cell.grid(row=r, column=col, padx=2, pady=2, sticky="nsew")
        self.cal_month_total.configure(text=f"Month total: {self._format_hms(round(month_total / 1000))}")

    def _on_calendar_day_click(self, key, ms):
        try:
            pretty = datetime.strptime(key, "%Y-%m-%d").strftime("%A, %d %b %Y")
        except Exception:
            pretty = key
        self._cal_selected_key = key
        if ms > 0:
            self.cal_detail.configure(text=f"{pretty}:  {self._format_hms(round(ms / 1000))} tracked")
            self.cal_edit_btn.grid(row=0, column=1, padx=(6, 0))
            self.cal_add_btn.grid(row=0, column=2, padx=(6, 0))
            self.cal_del_btn.grid(row=0, column=3, padx=(6, 0))
        else:
            self.cal_detail.configure(text=f"{pretty}:  no tracked time")
            self.cal_add_btn.grid(row=0, column=1, padx=(6, 0))
            self.cal_edit_btn.grid_remove()
            self.cal_del_btn.grid_remove()

    def _cal_edit_selected(self):
        if self._cal_selected_key:
            self._edit_day(self._cal_selected_key)

    def _cal_add_selected(self):
        if self._cal_selected_key:
            self._add_day_log(self._cal_selected_key)

    def _cal_delete_selected(self):
        if self._cal_selected_key:
            self._delete_days([self._cal_selected_key])

    # ---------------------------------------------------------------- settings io
    def _settings_path(self):
        return os.path.join(self._resource_dir(), SETTINGS_FILENAME)

    def _is_valid_date_key(self, value):
        try:
            datetime.strptime(str(value), "%Y-%m-%d")
            return True
        except Exception:
            return False

    def _safe_int(self, value, fallback=0):
        try:
            return int(value)
        except Exception:
            return fallback

    def _load_settings(self):
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self._settings_loaded = True
            return
        self.topmost_var.set(bool(data.get("topmost", self.topmost_var.get())))
        self.track_var.set(bool(data.get("track", self.track_var.get())))
        theme = str(data.get("theme", "dark")).lower()
        self.theme_var.set(theme if theme in ("dark", "light") else "dark")
        mode = str(data.get("mode", "timer"))
        self.mode_var.set(mode if mode in ("timer", "stopwatch") else "timer")
        cstyle = str(data.get("clock_style", "ring"))
        self.clock_style.set(cstyle if cstyle in CLOCK_STYLE_KEYS else "ring")
        preset_values = data.get("preset_minutes", self.preset_minutes)
        if isinstance(preset_values, list):
            cleaned = self._sanitize_preset_minutes(preset_values)
            if cleaned:
                self.preset_minutes = cleaned
        self.mini_shape.set(self._sanitize_mini_shape(data.get("mini_shape", self.mini_shape.get())))
        if hasattr(self, "mini_shape_display"):
            self.mini_shape_display.set(MINI_SHAPE_LABEL.get(self.mini_shape.get(), "Circle"))
        self.mini_size.set(max(MIN_MINI_SIZE, min(MAX_MINI_SIZE, self._safe_int(data.get("mini_size"), 220))))
        self.mini_ui_scale.set(max(MIN_MINI_UI_SCALE, min(MAX_MINI_UI_SCALE,
            self._safe_int(data.get("mini_ui_scale"), DEFAULT_MINI_UI_SCALE))))
        h = str(self._safe_int(data.get("hours"), 0))
        m = str(max(0, min(59, self._safe_int(data.get("minutes"), 25))))
        s = str(max(0, min(59, self._safe_int(data.get("seconds"), 0))))
        self._initial_hms = (h, m, s)
        self.save_stats_var.set(bool(data.get("save_stats", self.save_stats_var.get())))

        self.history = {}
        raw_history = data.get("history", {})
        if isinstance(raw_history, dict):
            for day, ms in raw_history.items():
                if self._is_valid_date_key(day):
                    self.history[day] = max(0, self._safe_int(ms, 0))

        stored_day = str(data.get("current_day", self._today_key()))
        self.current_day = self._today_key()
        legacy_today = max(0, self._safe_int(data.get("productive_ms_today"), 0))
        if self._is_valid_date_key(stored_day) and legacy_today > 0 and stored_day not in self.history:
            self.history[stored_day] = legacy_today
        self.productive_ms_today = self.history.get(self.current_day, 0)
        self._settings_loaded = True

    def _save_settings(self):
        if not self._settings_loaded:
            return
        payload = {
            "topmost": self.topmost_var.get(),
            "track": self.track_var.get(),
            "theme": self.theme_var.get(),
            "mode": self.mode_var.get(),
            "clock_style": self.clock_style.get(),
            "preset_minutes": self.preset_minutes,
            "mini_shape": self.mini_shape.get(),
            "mini_size": self.mini_size.get(),
            "mini_ui_scale": self.mini_ui_scale.get(),
            "hours": self._safe_int(self.var_h.get(), 0) if hasattr(self, "var_h") else 0,
            "minutes": self._safe_int(self.var_m.get(), 25) if hasattr(self, "var_m") else 25,
            "seconds": self._safe_int(self.var_s.get(), 0) if hasattr(self, "var_s") else 0,
            "save_stats": self.save_stats_var.get(),
            "history": {d: int(ms) for d, ms in self.history.items() if int(ms) > 0},
            "productive_ms_today": int(self.productive_ms_today),
            "current_day": self._today_key(),
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def _set_window_icon(self):
        icon_path = os.path.join(self._resource_dir(), "timericon.ico")
        if not os.path.exists(icon_path):
            return
        try:
            self.iconbitmap(icon_path)
        except Exception:
            pass

    def _center_window(self):
        self.update_idletasks()
        w, h = 1000, 660
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        x = int((sw - w) / 2); y = int((sh - h) / 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _beep(self):
        try:
            if IS_WINDOWS:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                print("\a", end="", flush=True)
        except Exception:
            pass

    def _cancel_tick(self):
        if self.tick_id is not None:
            try:
                self.after_cancel(self.tick_id)
            except Exception:
                pass
            self.tick_id = None

    def _now_ms(self):
        return int(time.time() * 1000)

    def _on_close(self):
        self._cancel_tick()
        self._save_settings()
        if self.mini_win and self.mini_win.winfo_exists():
            self.mini_win.destroy()
        self.destroy()

    # ---------------------------------------------------------------- audio
    def _resource_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _audio_path(self):
        base = self._resource_dir()
        candidate = os.path.join(base, AUDIO_FILENAME)
        if os.path.exists(candidate):
            return candidate
        alt = os.path.join(base, os.path.splitext(AUDIO_FILENAME)[0] + ".mp3")
        return alt if os.path.exists(alt) else None

    def _play_alarm(self):
        path = self._audio_path()
        if not path:
            self._beep()
            self._set_msg("Time's up! (No audio file found; beeped instead.)")
            return
        try:
            if IS_WINDOWS:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif IS_MAC:
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                player = None
                for cmd in ("paplay", "aplay", "play"):
                    if shutil.which(cmd):
                        player = cmd; break
                if player:
                    subprocess.Popen([player, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self._beep()
                    self._set_msg("Time's up! (No audio player found; beeped instead.)")
        except Exception:
            self._beep()
            self._set_msg("Time's up! (Audio failed; beeped instead.)")

    # ---------------------------------------------------------------- mini window
    def open_mini(self):
        shape = self.mini_shape.get()

        if self.mini_win and self.mini_win.winfo_exists():
            self.mini_win.destroy()

        self.mini_win = tk.Toplevel(self)
        self.mini_win.title("Mini Timer")
        self.mini_win.attributes("-topmost", True)
        try:
            icon_path = os.path.join(self._resource_dir(), "timericon.ico")
            if os.path.exists(icon_path):
                self.mini_win.iconbitmap(icon_path)
        except Exception:
            pass
        self.mini_win.resizable(False, False)
        self.mini_win.overrideredirect(True)

        size = self.mini_size.get()
        self.mini_win.geometry(f"{size}x{size}+100+100")

        self.mini_canvas = tk.Canvas(self.mini_win, width=size, height=size,
                                     highlightthickness=0, bg=self.mini_bg_trans)
        self.mini_canvas.pack(fill="both", expand=True)

        if IS_WINDOWS:
            self.mini_win.wm_attributes("-transparentcolor", self.mini_bg_trans)

        self._mini_draw_shape()
        self._mini_build_controls()
        self._mini_clock_sig = None
        self._mini_render()
        self._mini_update_buttons()

        self._install_resize_handlers()

    def _mini_build_controls(self):
        for item in getattr(self, "mini_window_items", []):
            try:
                self.mini_canvas.delete(item)
            except Exception:
                pass
        self.mini_window_items = []

        size = self.mini_size.get()
        layout = self._mini_layout(size)
        cx = layout["cx"]
        btn_span = int(layout["btn_span"])

        self._mini_figure = self.clock_style.get() in ("analog", "hourglass")
        self._mini_clock_sig = None
        time_font = self._mini_time_font(size)
        self.mini_time = tk.Label(self.mini_win, text="00:00:00",
                                  font=time_font, fg="#e5e7eb", bg="#1f2335")
        if not self._mini_figure:
            self.mini_window_items.append(
                self.mini_canvas.create_window(cx, layout["time_y"], window=self.mini_time)
            )

        btn_frame = tk.Frame(self.mini_win, bg="#1f2335",
                             width=btn_span, height=int(layout["btn_frame_h"]))
        self.mini_btn_frame = btn_frame
        btn_frame.grid_propagate(False)
        btn_frame.pack_propagate(False)

        btn_font = ("Segoe UI", layout["btn_font"], "bold")
        btn_specs = [
            ("\u25B6", self.on_start, "#22c55e", "#16a34a"),
            ("II", self.on_pause, "#f59e0b", "#d97706"),
            ("\u23F5", self.on_resume, "#3b82f6", "#2563eb"),
            ("\u25A0", self.on_stop, "#ef4444", "#dc2626"),
        ]
        self.mbtn_start = self.mbtn_pause = self.mbtn_resume = self.mbtn_stop = None
        btns = []
        gap = layout["btn_gap"]
        for i, (label, cmd, bg, abg) in enumerate(btn_specs):
            if layout["use_2x2"]:
                row, col = divmod(i, 2)
            else:
                row, col = 0, i
            b = tk.Button(btn_frame, text=label, width=2, height=1,
                          command=cmd, relief="flat", bg=bg, fg="white", font=btn_font,
                          activebackground=abg, activeforeground="white",
                          padx=layout["ipadx"], pady=layout["ipady"])
            b.grid(row=row, column=col, padx=gap, pady=gap, sticky="nsew")
            btn_frame.grid_columnconfigure(col, weight=1, uniform="mbtn")
            if layout["use_2x2"]:
                btn_frame.grid_rowconfigure(row, weight=1, uniform="mbtnr")
            btns.append(b)
        self.mbtn_start, self.mbtn_pause, self.mbtn_resume, self.mbtn_stop = btns

        self.mini_window_items.append(
            self.mini_canvas.create_window(cx, layout["btn_y"], window=btn_frame, anchor="center")
        )

        close_font = ("Segoe UI", max(8, layout["btn_font"]), "bold")
        close_btn = tk.Button(self.mini_win, text="\u00D7", width=2, height=1,
                              command=self.mini_win.destroy, relief="flat",
                              bg="#334155", fg="white", font=close_font,
                              activebackground="#475569", activeforeground="white",
                              padx=1, pady=0)
        self.mini_close_btn = close_btn
        self.mini_window_items.append(
            self.mini_canvas.create_window(layout["close_x"], layout["close_y"],
                                           window=close_btn, anchor="center")
        )

    def _mini_render(self):
        try:
            self.mini_time.config(text=self._format_hms(self.remaining_seconds))
        except Exception:
            pass
        self._mini_draw_clock()

    def _mini_draw_clock(self):
        style = self.clock_style.get()
        if style not in ("analog", "hourglass"):
            return
        s = self.mini_size.get()
        layout = self._mini_layout(s)
        pct = round(max(0.0, min(1.0, self._ring_pct)), 4)
        time_txt = self._format_hms(self.remaining_seconds)
        sig = (style, s, pct, time_txt, self.timer_state)
        if getattr(self, "_mini_clock_sig", None) == sig:
            return
        self._mini_clock_sig = sig

        for item in getattr(self, "mini_clock_items", []):
            try:
                self.mini_canvas.delete(item)
            except Exception:
                pass
        self.mini_clock_items = []

        cx = layout["cx"]
        cy = layout["clock_cy"]
        accent = self._accent_for_state()
        track = "#94a3b8"
        txt = "#e5e7eb"
        sand = "#f59e0b"
        add = self.mini_clock_items.append
        if style == "analog":
            R = s * 0.15
            if pct > 0:
                add(self.mini_canvas.create_arc(cx - R, cy - R, cx + R, cy + R, start=90,
                                                extent=-359.999 * pct, style="pieslice",
                                                fill=accent, outline=""))
            add(self.mini_canvas.create_oval(cx - R, cy - R, cx + R, cy + R, outline=track, width=2))
            ang = -pi / 2 + 2 * pi * pct
            add(self.mini_canvas.create_line(cx, cy, cx + R * 0.8 * cos(ang),
                                             cy + R * 0.8 * sin(ang), fill=txt, width=2))
            add(self.mini_canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=txt, outline=""))
        else:  # hourglass
            hw = s * 0.12
            hh = s * 0.15
            rf = 1 - pct
            for a, b in (((cx - hw, cy - hh), (cx + hw, cy - hh)),
                         ((cx - hw, cy + hh), (cx + hw, cy + hh)),
                         ((cx - hw, cy - hh), (cx, cy)), ((cx + hw, cy - hh), (cx, cy)),
                         ((cx - hw, cy + hh), (cx, cy)), ((cx + hw, cy + hh), (cx, cy))):
                add(self.mini_canvas.create_line(a[0], a[1], b[0], b[1], fill=track, width=2))
            if rf > 0.01:
                add(self.mini_canvas.create_polygon(cx, cy, cx - hw * rf, cy - hh * rf,
                                                    cx + hw * rf, cy - hh * rf, fill=sand, outline=""))
            if pct > 0.01:
                yl = cy + hh - hh * pct
                add(self.mini_canvas.create_polygon(cx - hw, cy + hh, cx + hw, cy + hh,
                                                    cx + hw * rf, yl, cx - hw * rf, yl,
                                                    fill=sand, outline=""))
        add(self.mini_canvas.create_text(cx, layout["btn_y"] - s * 0.14,
                                         text=self._format_hms(self.remaining_seconds),
                                         fill=txt, font=self._mini_time_font(s)))

    def _mini_update_buttons(self):
        mapping = {
            "idle":   ("normal", "disabled", "disabled", "disabled"),
            "running": ("disabled", "normal", "disabled", "normal"),
            "paused": ("disabled", "disabled", "normal", "normal"),
        }[self.timer_state]
        for btn, st in zip((self.mbtn_start, self.mbtn_pause, self.mbtn_resume, self.mbtn_stop), mapping):
            try:
                btn.config(state=st)
            except Exception:
                pass

    def _mini_draw_shape(self):
        for item in getattr(self, "mini_shape_items", []):
            try:
                self.mini_canvas.delete(item)
            except Exception:
                pass
        self.mini_shape_items = []

        s = self.mini_size.get()
        inset = max(6, int(s * 0.045))
        fill = "#1f2335"
        outline = "#3b82f6"
        shape = self.mini_shape.get()

        if shape == "circle":
            self._oval(inset, inset, s - inset, s - inset, fill, outline)
        elif shape == "rounded_rect":
            r = max(12, s // 8)
            self._round_rect(inset, inset, s - inset, s - inset, r, fill, outline)
        elif shape == "squircle":
            r = max(16, s // 3)
            self._round_rect(inset, inset, s - inset, s - inset, r, fill, outline)
        elif shape == "pod":
            r = (s - 2 * inset) // 2
            self._round_rect(inset, inset, s - inset, s - inset, r, fill, outline)
        elif shape == "hexagon":
            R = (s - 2 * inset) / 2
            cx, cy = s / 2, s / 2
            pts = []
            for i in range(6):
                ang = pi / 3 * i - pi / 2
                pts += [cx + R * cos(ang), cy + R * sin(ang)]
            self._poly(pts, fill, outline)
        elif shape == "diamond":
            cx, cy = s / 2, s / 2
            R = s / 2 - inset
            pts = [cx, cy - R, cx + R, cy, cx, cy + R, cx - R, cy]
            self._poly(pts, fill, outline)
        elif shape == "shield":
            self._draw_shield(s, fill, outline, inset)
        elif shape == "ring":
            self._oval(inset, inset, s - inset, s - inset, fill, outline)
            inner_margin = s * 0.28
            if IS_WINDOWS:
                self.mini_shape_items.append(
                    self.mini_canvas.create_oval(inner_margin, inner_margin, s - inner_margin, s - inner_margin,
                                                 fill=self.mini_bg_trans, outline=self.mini_bg_trans)
                )
            else:
                self._oval(inner_margin, inner_margin, s - inner_margin, s - inner_margin, "#1b2033", "#1b2033")
        else:
            self._oval(inset, inset, s - inset, s - inset, fill, outline)

    def _angle_to_resize_edge(self, ang):
        a = (ang + 2 * pi) % (2 * pi)
        if a < pi / 8 or a >= 15 * pi / 8:
            return "e"
        if a < 3 * pi / 8:
            return "se"
        if a < 5 * pi / 8:
            return "s"
        if a < 7 * pi / 8:
            return "sw"
        if a < 9 * pi / 8:
            return "w"
        if a < 11 * pi / 8:
            return "nw"
        if a < 13 * pi / 8:
            return "n"
        return "ne"

    def _mini_shape_resize_points(self, s):
        """Corner/vertex points on the drawn shape (opaque — clickable on Windows)."""
        inset = max(6, int(s * 0.045))
        cx = cy = s / 2.0
        R = s / 2.0 - inset
        shape = self.mini_shape.get()
        x0, y0, x1, y1 = inset, inset, s - inset, s - inset

        if shape == "diamond":
            return [
                (cx, cy - R, "n"), (cx + R, cy, "e"),
                (cx, cy + R, "s"), (cx - R, cy, "w"),
            ]
        if shape == "hexagon":
            return [
                (cx + R * cos(pi / 3 * i - pi / 2), cy + R * sin(pi / 3 * i - pi / 2),
                 self._angle_to_resize_edge(pi / 3 * i - pi / 2))
                for i in range(6)
            ]
        if shape == "shield":
            w = R
            top, bot = inset, s - inset
            mid_y = top + (bot - top) * 0.42
            verts = [
                (cx, top), (cx + w, top + (bot - top) * 0.18),
                (cx + w * 0.88, mid_y), (cx, bot),
                (cx - w * 0.88, mid_y), (cx - w, top + (bot - top) * 0.18),
            ]
            return [(px, py, self._angle_to_resize_edge(atan2(py - cy, px - cx)))
                    for px, py in verts]
        if shape == "pod":
            return [
                (cx, y0, "n"), (x1, cy, "e"),
                (cx, y1, "s"), (x0, cy, "w"),
            ]
        if shape in ("rounded_rect", "squircle"):
            return [
                (x0, y0, "nw"), (x1, y0, "ne"),
                (x1, y1, "se"), (x0, y1, "sw"),
            ]
        # circle, ring — diagonal points on the outline
        return [
            (cx + R * cos(ang), cy + R * sin(ang), self._angle_to_resize_edge(ang))
            for ang in (-pi / 4, pi / 4, 3 * pi / 4, -3 * pi / 4)
        ]

    def _draw_shield(self, s, fill, outline, inset):
        cx = s / 2
        w = s / 2 - inset
        top = inset
        bot = s - inset
        mid_y = top + (bot - top) * 0.42
        pts = [
            cx, top,
            cx + w, top + (bot - top) * 0.18,
            cx + w * 0.88, mid_y,
            cx, bot,
            cx - w * 0.88, mid_y,
            cx - w, top + (bot - top) * 0.18,
        ]
        self._poly(pts, fill, outline)

    def _oval(self, x0, y0, x1, y1, fill, outline):
        self.mini_shape_items.append(
            self.mini_canvas.create_oval(x0, y0, x1, y1, fill=fill, outline=outline, width=2)
        )

    def _poly(self, pts, fill, outline):
        self.mini_shape_items.append(
            self.mini_canvas.create_polygon(*pts, fill=fill, outline=outline, width=2, smooth=True)
        )

    def _round_rect(self, x0, y0, x1, y1, r, fill, outline):
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        items = []
        items.append(self.mini_canvas.create_arc(x0, y0, x0 + 2 * r, y0 + 2 * r, start=90, extent=90,
                                                 style="pieslice", outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_arc(x1 - 2 * r, y0, x1, y0 + 2 * r, start=0, extent=90,
                                                 style="pieslice", outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_arc(x1 - 2 * r, y1 - 2 * r, x1, y1, start=270, extent=90,
                                                 style="pieslice", outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_arc(x0, y1 - 2 * r, x0 + 2 * r, y1, start=180, extent=90,
                                                 style="pieslice", outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_rectangle(x0 + r, y0, x1 - r, y1, outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_rectangle(x0, y0 + r, x1, y1 - r, outline=outline, fill=fill, width=2))
        self.mini_shape_items += items

    def _install_resize_handlers(self):
        self._mini_drag_info = None
        for w in (self.mini_canvas, self.mini_win):
            for seq in ("<Motion>", "<ButtonPress-1>", "<ButtonRelease-1>", "<B1-Motion>"):
                try:
                    w.unbind(seq)
                except Exception:
                    pass
            w.bind("<Motion>", self._on_mini_motion)
            w.bind("<ButtonPress-1>", self._on_mini_press)
            w.bind("<ButtonRelease-1>", self._on_mini_release)
            w.bind("<B1-Motion>", self._on_mini_drag)

    def _mini_pointer_xy(self):
        if not (self.mini_canvas and self.mini_canvas.winfo_exists()):
            return 0, 0
        return (self.mini_win.winfo_pointerx() - self.mini_canvas.winfo_rootx(),
                self.mini_win.winfo_pointery() - self.mini_canvas.winfo_rooty())

    def _mini_event_xy(self, e):
        return self._mini_pointer_xy()

    def _hit_test_edge(self, x, y, w, h):
        m = RESIZE_MARGIN
        best = None
        best_d = m + 1
        for px, py, edge in self._mini_shape_resize_points(w):
            d = hypot(x - px, y - py)
            if d <= m and d < best_d:
                best_d = d
                best = edge
        return best

    def _cursor_for_edge(self, edge):
        return {
            "n": "top_side", "s": "bottom_side", "e": "right_side", "w": "left_side",
            "ne": "top_right_corner", "nw": "top_left_corner",
            "se": "bottom_right_corner", "sw": "bottom_left_corner"
        }.get(edge, "arrow")

    def _on_mini_motion(self, e):
        if not (self.mini_win and self.mini_win.winfo_exists()):
            return
        x, y = self._mini_event_xy(e)
        w = self.mini_canvas.winfo_width()
        h = self.mini_canvas.winfo_height()
        edge = self._hit_test_edge(x, y, w, h)
        self._resize_edge = edge
        try:
            cur = self._cursor_for_edge(edge) if edge else "arrow"
            self.mini_canvas.config(cursor=cur)
            self.mini_win.config(cursor=cur)
        except Exception:
            pass

    def _on_mini_press(self, e):
        if not (self.mini_win and self.mini_win.winfo_exists()):
            return
        x, y = self._mini_event_xy(e)
        w = self.mini_canvas.winfo_width()
        h = self.mini_canvas.winfo_height()
        self._resize_edge = self._hit_test_edge(x, y, w, h)
        if self._resize_edge:
            self._resize_active = True
            self._mini_drag_info = None
            self._press_info = (e.x_root, e.y_root,
                                self.mini_win.winfo_x(), self.mini_win.winfo_y(),
                                self.mini_size.get())
            try:
                self.mini_win.grab_set()
            except Exception:
                pass
            return "break"
        self._resize_active = False
        self._press_info = None
        if e.widget is self.mini_canvas:
            self._mini_drag_info = (e.x_root, e.y_root,
                                    self.mini_win.winfo_x(), self.mini_win.winfo_y())

    def _on_mini_release(self, e):
        was_resizing = self._resize_active
        self._resize_active = False
        self._press_info = None
        self._mini_drag_info = None
        try:
            self.mini_win.grab_release()
        except Exception:
            pass
        if was_resizing:
            self._save_settings()

    def _on_mini_drag(self, e):
        if self._resize_active and self._press_info:
            x0, y0, wx0, wy0, s0 = self._press_info
            dx, dy = e.x_root - x0, e.y_root - y0
            edge = self._resize_edge
            sign_x = 1 if edge in ("e", "ne", "se") else (-1 if edge in ("w", "nw", "sw") else 0)
            sign_y = 1 if edge in ("s", "se", "sw") else (-1 if edge in ("n", "ne", "nw") else 0)
            delta = max(sign_x * dx, sign_y * dy) if (sign_x and sign_y) else (sign_x * dx or sign_y * dy)
            new_s = int(max(MIN_MINI_SIZE, min(MAX_MINI_SIZE, s0 + delta)))
            if new_s == self.mini_size.get():
                return "break"
            pos_x, pos_y = wx0, wy0
            if edge in ("w", "nw", "sw"):
                pos_x = wx0 + (s0 - new_s)
            if edge in ("n", "ne", "nw"):
                pos_y = wy0 + (s0 - new_s)
            self.mini_size.set(new_s)
            self.mini_size_lbl.configure(text=f"{new_s} px")
            self.mini_win.geometry(f"{new_s}x{new_s}+{pos_x}+{pos_y}")
            self.mini_canvas.config(width=new_s, height=new_s)
            self._refresh_mini_window()
            return "break"
        if self._mini_drag_info and e.widget is self.mini_canvas:
            x0, y0, wx, wy = self._mini_drag_info
            dx, dy = e.x_root - x0, e.y_root - y0
            self.mini_win.geometry(f"+{wx + dx}+{wy + dy}")


if __name__ == "__main__":
    app = TimerApp()
    app.mainloop()
