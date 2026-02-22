# file: tiny_timer_mini_edge_resize_full.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import time, math, sys, os, shutil, subprocess
import json
from math import sin, cos, pi
from datetime import datetime

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# Mini view resize behavior
RESIZE_MARGIN = 12      # px near edges/corners that triggers resize
MIN_MINI_SIZE = 140
MAX_MINI_SIZE = 480

# Custom audio to play when timer completes.
# Place this file in the same folder as the .py (or the .exe after PyInstaller build).
AUDIO_FILENAME = "alarm.wav"   # .wav works on all platforms; macOS also supports .mp3 via afplay
SETTINGS_FILENAME = "timer_settings.json"

class TimerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tiny Timer + Productivity")
        self.geometry("430x310")
        self.minsize(360, 300)
        self.attributes("-topmost", True)

        # ---- timer state ----
        self.state = "idle"
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

        # ---- productivity (in-memory) ----
        self.track_var = tk.BooleanVar(value=True)
        self.productive_ms_today = 0
        self.current_day = self._today_key()

        # ---- UI state ----
        self.compact_var = tk.BooleanVar(value=True)
        self.topmost_var = tk.BooleanVar(value=True)
        self.mode_var = tk.StringVar(value="timer")
        self.theme_var = tk.StringVar(value="dark")
        self.mini_win = None
        self.mini_shape = tk.StringVar(value="fighter")  # default mini shape
        self.mini_size = tk.IntVar(value=220)            # square size (uniform)
        self.mini_bg_trans = "magenta"
        self.preset_minutes = [5, 15, 25, 50]
        self._initial_hms = ("0", "25", "0")
        self._settings_loaded = False

        # mini drag/resize internals
        self._resize_edge = None       # 'n','s','e','w','ne','nw','se','sw'
        self._resize_active = False
        self._press_info = None        # (x_root, y_root, win_x, win_y, size_at_press)

        self._load_settings()
        self._build_ui()
        self._set_window_icon()
        self._show_welcome()

        self.bind("<Return>", lambda e: self.on_start() if self.state == "idle" else None)
        self.bind("<space>", self._on_space_toggle)
        self.bind("<Escape>", lambda e: self.on_stop() if self.state != "idle" else None)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- Main UI ----------
    def _build_ui(self):
        root = ttk.Frame(self, padding=(10, 8))
        root.pack(fill="both", expand=True)
        self.root = root

        self.welcome_frame = ttk.Frame(root, padding=(10, 12))
        self.main_frame = ttk.Frame(root)

        ttk.Label(self.welcome_frame, text="Focus Timer", font=("Segoe UI", 20, "bold")).pack(pady=(4, 8))
        ttk.Label(self.welcome_frame, text="Choose your mode and theme to begin.").pack(pady=(0, 12))

        theme_row = ttk.Frame(self.welcome_frame); theme_row.pack(pady=(0, 16))
        ttk.Label(theme_row, text="Theme:").pack(side="left")
        ttk.Radiobutton(theme_row, text="Dark", value="dark",
                        variable=self.theme_var, command=self._on_theme_select).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(theme_row, text="Light", value="light",
                        variable=self.theme_var, command=self._on_theme_select).pack(side="left", padx=(10, 0))

        self.btn_welcome_timer = ttk.Button(self.welcome_frame, text="Focus Timer", width=24,
                                            command=lambda: self._enter_main("timer"))
        self.btn_welcome_timer.pack(pady=(4, 8))
        self.btn_welcome_stopwatch = ttk.Button(self.welcome_frame, text="Focus Stopwatch", width=24,
                                                command=lambda: self._enter_main("stopwatch"))
        self.btn_welcome_stopwatch.pack(pady=(0, 6))

        title_row = ttk.Frame(self.main_frame); title_row.pack(fill="x")
        ttk.Label(title_row, text="Focus Timer", font=("Segoe UI", 14, "bold")).pack(side="left")
        self.lbl_mode_hint = ttk.Label(title_row, text="Mode: Timer", foreground="#6b7280")
        self.lbl_mode_hint.pack(side="left", padx=(10, 0))
        nav_right = ttk.Frame(title_row); nav_right.pack(side="right")
        self.btn_switch_mode = ttk.Button(nav_right, text="Switch to Stopwatch",
                                          command=self._quick_switch_mode, width=18)
        self.btn_switch_mode.pack(side="left", padx=(0, 6))
        self.btn_home = ttk.Button(nav_right, text="Home", command=self._go_home, width=8)
        self.btn_home.pack(side="left", padx=(0, 8))
        self.chk_top = ttk.Checkbutton(title_row, text="Always on top",
                                       variable=self.topmost_var, command=self._toggle_topmost)
        self.chk_top.pack(side="right")
        ctrl_row = ttk.Frame(self.main_frame); ctrl_row.pack(fill="x", pady=(4, 0))
        self.chk_compact = ttk.Checkbutton(ctrl_row, text="Compact",
                                           variable=self.compact_var, command=self._apply_compact)
        self.chk_compact.pack(side="left")

        # mini selector
        mini_frame = ttk.Frame(ctrl_row); mini_frame.pack(side="right")
        ttk.Label(mini_frame, text="Mini Shape:").pack(side="left", padx=(0, 6))
        shapes = ["fighter","circle","rounded_rect","capsule","triangle","hexagon","star","ring"]
        if IS_WINDOWS: shapes += ["glove"]
        self.cmb_shape = ttk.Combobox(mini_frame, state="readonly", width=14, values=shapes)
        self.cmb_shape.set(self.mini_shape.get())
        self.cmb_shape.pack(side="left")
        self.btn_open_mini = ttk.Button(mini_frame, text="Open Mini", command=self.open_mini)
        self.btn_open_mini.pack(side="left", padx=6)

        # inputs
        self.inputs_wrap = ttk.Frame(self.main_frame); self.inputs_wrap.pack(fill="x", pady=(6, 0))
        self.var_h = tk.StringVar(value=self._initial_hms[0])
        self.var_m = tk.StringVar(value=self._initial_hms[1])
        self.var_s = tk.StringVar(value=self._initial_hms[2])
        self._add_number_field(self.inputs_wrap, "Hrs", self.var_h, 0, 0, 0, 99)
        self._add_number_field(self.inputs_wrap, "Min", self.var_m, 0, 1, 0, 59)
        self._add_number_field(self.inputs_wrap, "Sec", self.var_s, 0, 2, 0, 59)

        self.presets_wrap = ttk.Frame(self.main_frame); self.presets_wrap.pack(fill="x", pady=(6, 0))
        ttk.Label(self.presets_wrap, text="Quick presets:").pack(side="left")
        self.preset_buttons = []
        self.btn_customize_presets = None
        self._build_preset_buttons()

        # display + progress
        self.lbl_time = ttk.Label(self.main_frame, text="00:00:00", font=("Consolas", 36, "bold"), anchor="center")
        self.lbl_time.pack(pady=(10, 4), fill="x")
        self.progress = ttk.Progressbar(self.main_frame, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.lbl_eta = ttk.Label(self.main_frame, text="Ends at: --:--:--", foreground="#6b7280")
        self.lbl_eta.pack(anchor="center", pady=(3, 0))

        # productivity
        self.prod_row = ttk.Frame(self.main_frame); self.prod_row.pack(fill="x", pady=(8, 0))
        self.chk_track = ttk.Checkbutton(self.prod_row, text="Track Productivity (adds while running)",
                                         variable=self.track_var)
        self.chk_track.pack(side="left")
        self.lbl_today = ttk.Label(self.prod_row, text="Today: 00:00:00", font=("Segoe UI", 10, "bold"))
        self.lbl_today.pack(side="left", padx=10)
        self.btn_reset_tracked = ttk.Button(self.prod_row, text="Reset",
                                            command=self.on_reset_tracked, width=8)
        self.btn_reset_tracked.pack(side="right")

        # status + controls
        self.var_msg = tk.StringVar(value="")
        ttk.Label(self.main_frame, textvariable=self.var_msg, foreground="#6b7280").pack(pady=(6, 0))
        btns = ttk.Frame(self.main_frame); btns.pack(pady=(8, 0))
        self.btn_start  = ttk.Button(btns, text="Start",  width=8, command=self.on_start)
        self.btn_pause  = ttk.Button(btns, text="Pause",  width=8, command=self.on_pause)
        self.btn_resume = ttk.Button(btns, text="Resume", width=8, command=self.on_resume)
        self.btn_stop   = ttk.Button(btns, text="Stop",   width=8, command=self.on_stop)
        for i, b in enumerate((self.btn_start,self.btn_pause,self.btn_resume,self.btn_stop)):
            b.grid(row=0, column=i, padx=6)

        self._theme_available = False
        try:
            self.call("source", "sun-valley.tcl")
            self._theme_available = True
        except tk.TclError:
            self._theme_available = False
        self._apply_theme(self.theme_var.get())
        self._style_buttons()

    def _style_buttons(self):
        style = ttk.Style(self)
        try:
            style.configure("Primary.TButton", padding=(10, 6), font=("Segoe UI", 10, "bold"))
            style.configure("Secondary.TButton", padding=(8, 5), font=("Segoe UI", 9))
        except tk.TclError:
            return

        for btn in (self.btn_welcome_timer, self.btn_welcome_stopwatch, self.btn_start):
            btn.configure(style="Primary.TButton")
        for btn in (self.btn_pause, self.btn_resume, self.btn_stop, self.btn_home,
                    self.btn_switch_mode, self.btn_open_mini, self.btn_reset_tracked):
            btn.configure(style="Secondary.TButton")
        for btn in getattr(self, "preset_buttons", []):
            btn.configure(style="Secondary.TButton")
        if getattr(self, "btn_customize_presets", None):
            self.btn_customize_presets.configure(style="Secondary.TButton")

    def _build_preset_buttons(self):
        for btn in getattr(self, "preset_buttons", []):
            try:
                btn.destroy()
            except Exception:
                pass
        self.preset_buttons = []

        if getattr(self, "btn_customize_presets", None):
            try:
                self.btn_customize_presets.destroy()
            except Exception:
                pass
            self.btn_customize_presets = None

        for mins in self.preset_minutes:
            btn = ttk.Button(self.presets_wrap, text=f"{mins}m",
                             command=lambda m=mins: self._apply_preset(m), width=5)
            btn.pack(side="left", padx=(6, 0))
            self.preset_buttons.append(btn)

        self.btn_customize_presets = ttk.Button(self.presets_wrap, text="Customize",
                                                command=self._customize_presets, width=10)
        self.btn_customize_presets.pack(side="left", padx=(8, 0))

    def _add_number_field(self, parent, label, var, r, c, mn, mx):
        wrap = ttk.Frame(parent); wrap.grid(row=r, column=c, padx=6)
        ttk.Label(wrap, text=label).pack(anchor="w")
        vcmd = (self.register(self._validate_numeric), "%P")
        ent = ttk.Entry(wrap, textvariable=var, width=5, justify="center",
                        validate="key", validatecommand=vcmd)
        ent.pack()
        ent.bind("<FocusOut>", lambda e, v=var, a=(mn, mx): self._clamp_var(v, *a))
        ent.bind("<KeyRelease>", lambda e: self._preview_time())

    def _apply_compact(self):
        if self.compact_var.get():
            self.inputs_wrap.forget(); self.presets_wrap.forget(); self.prod_row.forget()
            self.geometry("320x180")
            self.lbl_time.configure(font=("Consolas", 30, "bold"))
        else:
            self.inputs_wrap.pack(fill="x", pady=(6, 0))
            self.presets_wrap.pack(fill="x", pady=(6, 0))
            self.prod_row.pack(fill="x", pady=(8, 0))
            self.geometry("430x390")
            self.lbl_time.configure(font=("Consolas", 36, "bold"))
        self.update_idletasks()
        if self._settings_loaded:
            self._save_settings()

    def _toggle_topmost(self):
        self.attributes("-topmost", self.topmost_var.get())
        if self._settings_loaded:
            self._save_settings()

    def _show_welcome(self):
        self.main_frame.pack_forget()
        self.welcome_frame.pack(fill="both", expand=True)
        self.title("Focus Timer")
        self.geometry("430x300")
        self._apply_theme(self.theme_var.get())
        if self._settings_loaded:
            self._save_settings()

    def _update_mode_hint(self):
        is_timer = self.mode_var.get() == "timer"
        self.lbl_mode_hint.config(text=f"Mode: {'Timer' if is_timer else 'Stopwatch'}")
        self.btn_switch_mode.config(text="Switch to Stopwatch" if is_timer else "Switch to Timer")

    def _quick_switch_mode(self):
        if self.state != "idle":
            self._set_msg("Stop the current session before switching mode.")
            return
        target = "stopwatch" if self.mode_var.get() == "timer" else "timer"
        self._enter_main(target)

    def _go_home(self):
        if self.state != "idle":
            self._set_msg("Stop the current session before going Home.")
            return
        self._show_welcome()

    def _enter_main(self, mode):
        self.mode_var.set("stopwatch" if mode == "stopwatch" else "timer")
        self.welcome_frame.pack_forget()
        self.main_frame.pack(fill="both", expand=True)
        self._update_mode_hint()
        self._apply_compact()
        self._set_buttons()
        self._update_today_label()
        self._set_inputs_enabled(True)
        if self.mode_var.get() == "timer":
            self.title("Focus Timer")
            self.remaining_seconds = self._calc_total_seconds()
            self.stopwatch_target_seconds = 0
            self._render(self.remaining_seconds)
            self._set_msg("Focus Timer ready.")
        else:
            self.title("Focus Stopwatch")
            self.total_seconds = 0
            self.stopwatch_elapsed_seconds = 0
            self.stopwatch_base_elapsed = 0
            self.stopwatch_start_ms = 0
            self.stopwatch_target_seconds = self._calc_total_seconds()
            self.remaining_seconds = 0
            self._render(0)
            self._set_msg("Focus Stopwatch ready.")
        self._update_eta_label()
        self._save_settings()

    def _on_theme_select(self):
        self._apply_theme(self.theme_var.get())
        self._style_buttons()
        self._save_settings()

    def _apply_theme(self, theme_name):
        # Uses Sun Valley theme when available; falls back to built-in ttk themes.
        if getattr(self, "_theme_available", False):
            try:
                self.call("set_theme", "dark" if theme_name == "dark" else "light")
                return
            except tk.TclError:
                pass
        style = ttk.Style(self)
        fallback = "clam" if theme_name == "light" else "alt"
        try:
            style.theme_use(fallback)
        except tk.TclError:
            pass

    # ---------- Validation / Formatting ----------
    def _validate_numeric(self, p): return (p == "" or (p.isdigit() and len(p) <= 3))
    def _clamp_var(self, var, mn, mx):
        try: v = int(var.get())
        except ValueError: v = 0
        var.set(str(max(mn, min(mx, v))))
    def _format_hms(self, s):
        s = max(0, int(s)); h = s//3600; m=(s%3600)//60; return f"{h:02d}:{m:02d}:{s%60:02d}"
    def _calc_total_seconds(self):
        self._clamp_var(self.var_h,0,99); self._clamp_var(self.var_m,0,59); self._clamp_var(self.var_s,0,59)
        try: h=int(self.var_h.get() or "0"); m=int(self.var_m.get() or "0"); s=int(self.var_s.get() or "0")
        except ValueError: return 0
        return h*3600 + m*60 + s

    def _current_elapsed_seconds(self):
        if self.state == "running":
            return self.stopwatch_base_elapsed + max(0, math.floor((self._now_ms() - self.stopwatch_start_ms)/1000))
        return self.stopwatch_base_elapsed

    # ---------- Timer controls ----------
    def on_start(self):
        if self.state != "idle": return
        if self.welcome_frame.winfo_ismapped():
            return
        if self.mode_var.get() == "timer":
            self.total_seconds = self._calc_total_seconds()
            if self.total_seconds <= 0:
                messagebox.showwarning("Invalid time","Please enter a time greater than 0 seconds."); return
            self.remaining_seconds = self.total_seconds
            self.end_at_ms = self._now_ms() + self.remaining_seconds*1000
        else:
            self.total_seconds = 0
            self.stopwatch_base_elapsed = 0
            self.stopwatch_start_ms = self._now_ms()
            self.stopwatch_elapsed_seconds = 0
            self.stopwatch_target_seconds = self._calc_total_seconds()
            self.remaining_seconds = 0
        self.last_tick_ms = self._now_ms()
        self.state = "running"; self._set_buttons(); self._set_inputs_enabled(False)
        self._update_eta_label()
        self._set_msg("Started."); self._tick()

    def on_pause(self):
        if self.state != "running": return
        self._apply_productivity_delta()
        if self.mode_var.get() == "timer":
            self.remaining_seconds = max(0, math.ceil((self.end_at_ms - self._now_ms())/1000))
        else:
            self.stopwatch_base_elapsed = self._current_elapsed_seconds()
            self.stopwatch_elapsed_seconds = self.stopwatch_base_elapsed
            self.remaining_seconds = self.stopwatch_elapsed_seconds
        self._cancel_tick(); self.state = "paused"; self._set_buttons(); self._set_msg("Paused.")
        self._update_eta_label()

    def on_resume(self):
        if self.state != "paused": return
        if self.mode_var.get() == "timer":
            if self.remaining_seconds <= 0: return
            self.end_at_ms = self._now_ms() + self.remaining_seconds*1000
        else:
            self.stopwatch_start_ms = self._now_ms()
            self.remaining_seconds = self.stopwatch_base_elapsed
        self.last_tick_ms = self._now_ms()
        self.state = "running"; self._set_buttons(); self._set_msg("Resumed."); self._tick()
        self._update_eta_label()

    def on_stop(self):
        self._apply_productivity_delta()
        self._cancel_tick(); self.state = "idle"
        self.stopwatch_elapsed_seconds = 0
        self.stopwatch_base_elapsed = 0
        self.stopwatch_start_ms = 0
        self.stopwatch_target_seconds = self._calc_total_seconds() if self.mode_var.get() == "stopwatch" else 0
        self.total_seconds = 0; self.remaining_seconds = 0
        self._render(0); self._set_buttons(); self._set_inputs_enabled(True); self._set_msg("Stopped.")
        self._update_eta_label()
        self._save_settings()

    def on_reset_tracked(self):
        self.productive_ms_today = 0; self._update_today_label(); self._set_msg("Tracked time reset to 0.")
        self._save_settings()

    # ---------- Tick / Productivity ----------
    def _tick(self):
        now = self._now_ms()
        if self._today_key() != self.current_day:
            self.current_day = self._today_key()
            self.productive_ms_today = 0
            self._update_today_label()

        if self.mode_var.get() == "timer":
            left = max(0, math.ceil((self.end_at_ms - now)/1000))
            self.remaining_seconds = left
            self._render(left)
        else:
            self.stopwatch_elapsed_seconds = self._current_elapsed_seconds()
            self.remaining_seconds = self.stopwatch_elapsed_seconds
            self._render(self.stopwatch_elapsed_seconds)

        if self.state == "running" and self.track_var.get() and self.last_tick_ms is not None:
            delta = max(0, now - self.last_tick_ms)
            self.productive_ms_today += delta
            self._update_today_label()
        self.last_tick_ms = now

        if self.mode_var.get() == "timer" and left <= 0:
            self.state = "idle"; self._set_buttons(); self._set_inputs_enabled(True)
            self._set_msg("Time's up!")
            self._update_eta_label()
            self._play_alarm()   # <-- play custom audio (with fallback)
            self._save_settings()
            return
        if self.mode_var.get() == "stopwatch" and self.stopwatch_target_seconds > 0 and self.stopwatch_elapsed_seconds >= self.stopwatch_target_seconds:
            self.state = "idle"; self._set_buttons(); self._set_inputs_enabled(True)
            self._set_msg("Stopwatch complete!")
            self._update_eta_label()
            self._play_alarm()
            self._save_settings()
            return
        self.tick_id = self.after(100, self._tick)

    def _apply_productivity_delta(self):
        if self.state == "running" and self.track_var.get() and self.last_tick_ms is not None:
            now = self._now_ms()
            self.productive_ms_today += max(0, now - self.last_tick_ms)
            self._update_today_label()
            self.last_tick_ms = now

    # ---------- Helpers ----------
    def _render(self, seconds_left):
        if seconds_left != self.last_whole:
            self.lbl_time.config(text=self._format_hms(seconds_left))
            self.last_whole = seconds_left
        if self.mode_var.get() == "timer":
            pct = 0 if self.total_seconds <= 0 else (1 - seconds_left/self.total_seconds)*100
        else:
            pct = 0
        self.progress["value"] = max(0, min(100, pct))
        if self.mini_win and self.mini_win.winfo_exists(): self._mini_render()
        self._update_eta_label()

    def _set_buttons(self):
        states = {
            "idle":   ("normal","disabled","disabled","disabled"),
            "running":("disabled","normal","disabled","normal"),
            "paused": ("disabled","disabled","normal","normal"),
        }[self.state]
        for btn, st in zip((self.btn_start,self.btn_pause,self.btn_resume,self.btn_stop), states):
            btn.config(state=st)
        if self.mini_win and self.mini_win.winfo_exists(): self._mini_update_buttons()

    def _set_inputs_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for child in self.inputs_wrap.winfo_children():
            for sub in child.winfo_children():
                if isinstance(sub, ttk.Entry): sub.config(state=state)
        for btn in getattr(self, "preset_buttons", []):
            btn.config(state=state)
        if getattr(self, "btn_customize_presets", None):
            self.btn_customize_presets.config(state=state)

    def _set_msg(self, text): self.var_msg.set(text or "")
    def _update_today_label(self):
        s = round(self.productive_ms_today/1000)
        self.lbl_today.config(text=f"Today: {s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}")
        # (mini is minimal; omit total display there)

    def _today_key(self): return datetime.now().strftime("%Y-%m-%d")
    def _update_eta_label(self):
        if self.mode_var.get() == "stopwatch":
            if self.stopwatch_target_seconds > 0:
                self.lbl_eta.config(
                    text=f"Elapsed: {self._format_hms(self.remaining_seconds)} / Target: {self._format_hms(self.stopwatch_target_seconds)}"
                )
            else:
                self.lbl_eta.config(text=f"Elapsed: {self._format_hms(self.remaining_seconds)}")
        elif self.state == "running":
            end_dt = datetime.fromtimestamp(self.end_at_ms/1000)
            self.lbl_eta.config(text=f"Ends at: {end_dt.strftime('%H:%M:%S')}")
        elif self.state == "paused" and self.remaining_seconds > 0:
            self.lbl_eta.config(text="Ends at: paused")
        else:
            self.lbl_eta.config(text="Ends at: --:--:--")

    def _on_space_toggle(self, _event=None):
        if self.welcome_frame.winfo_ismapped():
            return "break"
        if self.state == "idle":
            self.on_start()
        elif self.state == "running":
            self.on_pause()
        elif self.state == "paused":
            self.on_resume()
        return "break"

    def _apply_preset(self, minutes):
        if self.state != "idle":
            return
        self.var_h.set("0")
        self.var_m.set(str(minutes))
        self.var_s.set("0")
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

    def _customize_presets(self):
        if self.state != "idle":
            self._set_msg("Stop the current session before editing presets.")
            return
        current = ",".join(str(v) for v in self.preset_minutes)
        raw = simpledialog.askstring(
            "Customize Presets",
            "Enter preset minutes separated by commas (1-999).\nExample: 5,15,25,50",
            initialvalue=current,
            parent=self
        )
        if raw is None:
            return
        values = [p.strip() for p in raw.split(",") if p.strip()]
        new_values = self._sanitize_preset_minutes(values)
        if not new_values:
            messagebox.showwarning("Invalid presets", "Please enter at least one valid minute value.")
            return
        self.preset_minutes = new_values
        self._build_preset_buttons()
        self._style_buttons()
        self._set_msg("Quick presets updated.")
        self._save_settings()

    def _on_mode_change(self):
        if self.state != "idle":
            # Prevent switching modes mid-session to avoid inconsistent state.
            target = "timer" if self.mode_var.get() == "stopwatch" else "stopwatch"
            self.mode_var.set(target)
            self._set_msg("Stop the current session before switching mode.")
            return
        if self.mode_var.get() == "timer":
            self.remaining_seconds = self._calc_total_seconds()
            self._render(self.remaining_seconds)
            self._set_msg("Focus Timer mode selected.")
        else:
            self.total_seconds = 0
            self.remaining_seconds = 0
            self.stopwatch_elapsed_seconds = 0
            self.stopwatch_base_elapsed = 0
            self.stopwatch_start_ms = 0
            self._render(0)
            self._set_msg("Focus Stopwatch mode selected.")
        self._set_inputs_enabled(True)
        self._update_eta_label()
        self._save_settings()

    def _settings_path(self):
        return os.path.join(self._resource_dir(), SETTINGS_FILENAME)

    def _load_settings(self):
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self._settings_loaded = True
            return
        self.compact_var.set(bool(data.get("compact", self.compact_var.get())))
        self.topmost_var.set(bool(data.get("topmost", self.topmost_var.get())))
        self.track_var.set(bool(data.get("track", self.track_var.get())))
        theme = str(data.get("theme", "dark")).lower()
        self.theme_var.set(theme if theme in ("dark", "light") else "dark")
        mode = str(data.get("mode", "timer"))
        self.mode_var.set(mode if mode in ("timer", "stopwatch") else "timer")
        preset_values = data.get("preset_minutes", self.preset_minutes)
        if isinstance(preset_values, list):
            cleaned = self._sanitize_preset_minutes(preset_values)
            if cleaned:
                self.preset_minutes = cleaned
        self.mini_shape.set(str(data.get("mini_shape", self.mini_shape.get())))
        self.mini_size.set(max(MIN_MINI_SIZE, min(MAX_MINI_SIZE, self._safe_int(data.get("mini_size"), 220))))
        h = str(self._safe_int(data.get("hours"), 0))
        m = str(max(0, min(59, self._safe_int(data.get("minutes"), 25))))
        s = str(max(0, min(59, self._safe_int(data.get("seconds"), 0))))
        self._initial_hms = (h, m, s)
        stored_day = str(data.get("current_day", self._today_key()))
        self.current_day = self._today_key()
        if stored_day == self.current_day:
            self.productive_ms_today = max(0, self._safe_int(data.get("productive_ms_today"), 0))
        else:
            self.productive_ms_today = 0
        self._settings_loaded = True

    def _safe_int(self, value, fallback=0):
        try:
            return int(value)
        except Exception:
            return fallback

    def _save_settings(self):
        payload = {
            "compact": self.compact_var.get(),
            "topmost": self.topmost_var.get(),
            "track": self.track_var.get(),
            "theme": self.theme_var.get(),
            "mode": self.mode_var.get(),
            "preset_minutes": self.preset_minutes,
            "mini_shape": self.mini_shape.get(),
            "mini_size": self.mini_size.get(),
            "hours": self._safe_int(self.var_h.get(), 0) if hasattr(self, "var_h") else 0,
            "minutes": self._safe_int(self.var_m.get(), 25) if hasattr(self, "var_m") else 25,
            "seconds": self._safe_int(self.var_s.get(), 0) if hasattr(self, "var_s") else 0,
            "productive_ms_today": int(self.productive_ms_today),
            "current_day": self._today_key(),
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def _set_window_icon(self):
        # Best effort: uses timericon.ico if present beside script/exe.
        icon_path = os.path.join(self._resource_dir(), "timericon.ico")
        if not os.path.exists(icon_path):
            return
        try:
            self.iconbitmap(icon_path)
        except Exception:
            pass

    def _beep(self):
        try:
            if IS_WINDOWS:
                import winsound; winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else: print("\a", end="", flush=True)
        except Exception: pass
    def _cancel_tick(self):
        if self.tick_id is not None:
            try: self.after_cancel(self.tick_id)
            except Exception: pass
            self.tick_id = None
    def _now_ms(self): return int(time.time()*1000)
    def _preview_time(self):
        if self.state == "idle":
            if self.mode_var.get() == "timer":
                shown = self._calc_total_seconds()
                self.stopwatch_target_seconds = 0
            else:
                shown = 0
                self.stopwatch_target_seconds = self._calc_total_seconds()
            self._render(shown)
            self._set_msg("")
    def _on_close(self):
        self._cancel_tick()
        self._save_settings()
        if self.mini_win and self.mini_win.winfo_exists(): self.mini_win.destroy()
        self.destroy()

    # ---------- Custom audio (cross-platform best effort) ----------
    def _resource_dir(self):
        # Return the folder next to the running script, or the PyInstaller bundle folder for .exe
        if getattr(sys, "frozen", False):
            # If the audio sits *next to* the .exe, prefer the executable folder
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _audio_path(self):
        # Look for AUDIO_FILENAME in the resource dir
        base = self._resource_dir()
        candidate = os.path.join(base, AUDIO_FILENAME)
        if os.path.exists(candidate):
            return candidate
        # small convenience: allow alarm.mp3 as an alternative (mac/linux)
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
                # winsound supports .wav (async, non-blocking)
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif IS_MAC:
                # macOS built-in player
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # Linux: try paplay -> aplay -> play
                player = None
                for cmd in ("paplay", "aplay", "play"):
                    if shutil.which(cmd):
                        player = cmd; break
                if player:
                    subprocess.Popen([player, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # last resort
                    self._beep()
                    self._set_msg("Time's up! (No audio player found; beeped instead.)")
        except Exception:
            # never crash UI for audio
            self._beep()
            self._set_msg("Time's up! (Audio failed; beeped instead.)")

    # ---------- Mini (shaped, edge/corner resize + drag) ----------
    def open_mini(self):
        shape = self.cmb_shape.get()
        self.mini_shape.set(shape)

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
        self.mini_win.resizable(False, False)      # we handle resizing manually
        self.mini_win.overrideredirect(True)       # borderless for transparent shape

        size = self.mini_size.get()
        self.mini_win.geometry(f"{size}x{size}+100+100")

        self.mini_canvas = tk.Canvas(self.mini_win, width=size, height=size,
                                     highlightthickness=0, bg=self.mini_bg_trans)
        self.mini_canvas.pack(fill="both", expand=True)

        if IS_WINDOWS:
            self.mini_win.wm_attributes("-transparentcolor", self.mini_bg_trans)

        # draw + embed
        self._mini_draw_shape()
        self._mini_build_controls()
        self._mini_render()
        self._mini_update_buttons()

        # movement (drag anywhere inside when not resizing)
        self._enable_drag(self.mini_canvas)
        self._enable_drag(self.mini_win)  # also allow dragging when clicking over widgets

        # install edge/corner resize (no slider)
        self._install_resize_handlers()

    def _mini_build_controls(self):
        for item in getattr(self, "mini_window_items", []):
            try: self.mini_canvas.delete(item)
            except Exception: pass
        self.mini_window_items = []

        size = self.mini_size.get()
        cx, cy = size//2, size//2

        self.mini_time = tk.Label(self.mini_win, text="00:00:00",
                                  font=("Consolas", max(12, size//12), "bold"),
                                  fg="#e5e7eb", bg="#1f2335")
        self.mini_window_items.append(
            self.mini_canvas.create_window(cx, int(cy - size*0.20), window=self.mini_time)
        )

        btn_frame = ttk.Frame(self.mini_win)
        self.mbtn_start  = ttk.Button(btn_frame, text="▶", width=3, command=self.on_start)
        self.mbtn_pause  = ttk.Button(btn_frame, text="II", width=3, command=self.on_pause)
        self.mbtn_resume = ttk.Button(btn_frame, text="⏵", width=3, command=self.on_resume)
        self.mbtn_stop   = ttk.Button(btn_frame, text="■", width=3, command=self.on_stop)
        for i, b in enumerate((self.mbtn_start, self.mbtn_pause, self.mbtn_resume, self.mbtn_stop)):
            b.grid(row=0, column=i, padx=2)
        self.mini_window_items.append(
            self.mini_canvas.create_window(cx, int(cy - size*0.02), window=btn_frame)
        )

        close_btn = ttk.Button(self.mini_win, text="×", width=2, command=self.mini_win.destroy)
        self.mini_window_items.append(self.mini_canvas.create_window(size-18, 18, window=close_btn))

    def _mini_render(self):
        self.mini_time.config(text=self._format_hms(self.remaining_seconds))

    def _mini_update_buttons(self):
        mapping = {
            "idle":   ("normal","disabled","disabled","disabled"),
            "running":("disabled","normal","disabled","normal"),
            "paused": ("disabled","disabled","normal","normal"),
        }[self.state]
        for btn, st in zip((self.mbtn_start,self.mbtn_pause,self.mbtn_resume,self.mbtn_stop), mapping):
            try: btn.config(state=st)
            except Exception: pass

    def _mini_draw_shape(self):
        for item in getattr(self, "mini_shape_items", []):
            try: self.mini_canvas.delete(item)
            except Exception: pass
        self.mini_shape_items = []

        s = self.mini_size.get()
        inset = 4
        fill = "#1f2335"; outline = "#3b3f58"
        shape = self.mini_shape.get()

        if shape == "circle":
            self._oval(inset, inset, s-inset, s-inset, fill, outline)

        elif shape == "rounded_rect":
            r = max(10, s//7); self._round_rect(inset, inset, s-inset, s-inset, r, fill, outline)

        elif shape == "capsule":
            r = s//2; self._round_rect(inset, s*0.25, s-inset, s*0.75, r, fill, outline)

        elif shape == "triangle":
            pts = [s/2, inset,  s-inset, s-inset,  inset, s-inset]
            self._poly(pts, fill, outline)

        elif shape == "hexagon":
            R = (s - 2*inset)/2; cx, cy = s/2, s/2
            pts = []
            for i in range(6):
                ang = pi/3 * i - pi/2
                pts += [cx + R*cos(ang), cy + R*sin(ang)]
            self._poly(pts, fill, outline)

        elif shape == "star":
            cx, cy = s/2, s/2; outer = (s - 2*inset)/2; inner = outer*0.45
            pts=[]
            for i in range(10):
                ang = pi/5 * i - pi/2
                r = outer if i%2==0 else inner
                pts += [cx + r*cos(ang), cy + r*sin(ang)]
            self._poly(pts, fill, outline)

        elif shape == "ring":
            self._oval(inset, inset, s-inset, s-inset, fill, outline)
            inner_margin = s*0.28
            if IS_WINDOWS:
                self.mini_shape_items.append(
                    self.mini_canvas.create_oval(inner_margin, inner_margin, s-inner_margin, s-inner_margin,
                                                 fill=self.mini_bg_trans, outline=self.mini_bg_trans)
                )
            else:
                self._oval(inner_margin, inner_margin, s-inner_margin, s-inner_margin, "#1b2033", "#1b2033")

        elif shape == "glove" and IS_WINDOWS:
            base_w, base_h = 240, 230
            scale = s / max(base_w, base_h)
            def sc(x,y): return (x*scale, y*scale + (s-base_h*scale)/2)
            body = [sc(40,30), sc(190,30), sc(210,80), sc(200,140),
                    sc(160,185), sc(120,200), sc(80,190), sc(50,150), sc(35,90)]
            flat=[]; [flat.extend(p) for p in body]
            self._poly(flat, fill, outline)
            x0,y0 = sc(150,60); x1,y1 = sc(210,120)
            self._oval(x0,y0,x1,y1,fill,outline)

        elif shape == "fighter":
            self._draw_fighter(s, fill, outline)

        else:
            self._oval(inset, inset, s-inset, s-inset, fill, outline)

    # --- shape helpers ---
    def _oval(self, x0, y0, x1, y1, fill, outline):
        self.mini_shape_items.append(
            self.mini_canvas.create_oval(x0, y0, x1, y1, fill=fill, outline=outline, width=2)
        )

    def _poly(self, pts, fill, outline):
        self.mini_shape_items.append(
            self.mini_canvas.create_polygon(*pts, fill=fill, outline=outline, width=2, smooth=True)
        )

    def _round_rect(self, x0, y0, x1, y1, r, fill, outline):
        r = min(r, (x1-x0)/2, (y1-y0)/2)
        items=[]
        items.append(self.mini_canvas.create_arc(x0, y0, x0+2*r, y0+2*r, start=90, extent=90,
                                                 style="pieslice", outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_arc(x1-2*r, y0, x1, y0+2*r, start=0, extent=90,
                                                 style="pieslice", outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_arc(x1-2*r, y1-2*r, x1, y1, start=270, extent=90,
                                                 style="pieslice", outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_arc(x0, y1-2*r, x0+2*r, y1, start=180, extent=90,
                                                 style="pieslice", outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_rectangle(x0+r, y0, x1-r, y1, outline=outline, fill=fill, width=2))
        items.append(self.mini_canvas.create_rectangle(x0, y0+r, x1, y1-r, outline=outline, fill=fill, width=2))
        self.mini_shape_items += items

    def _draw_fighter(self, s, fill, outline):
        """
        Stylized Muay Thai/boxing stance silhouette (torso/arms/legs/head).
        Coordinates normalized to 240x240 and scaled to 's'.
        """
        base = 240
        k = s / base
        def P(x,y): return (x*k, y*k)

        torso = [P(110,60), P(150,60), P(170,110), P(160,160), P(120,170), P(95,130)]
        r_arm = [P(150,70), P(185,85), P(195,110), P(170,115)]
        l_arm = [P(110,70), P(85,85),  P(80,110),  P(105,115)]
        r_leg = [P(140,170), P(160,210), P(150,225), P(130,185)]
        l_leg = [P(120,170), P(105,200), P(120,215), P(135,185)]

        def flat(seq): out=[]; [out.extend(p) for p in seq]; return out
        self._poly(flat(torso), fill, outline)
        self._poly(flat(r_arm), fill, outline)
        self._poly(flat(l_arm), fill, outline)
        self._poly(flat(r_leg), fill, outline)
        self._poly(flat(l_leg), fill, outline)

        hx, hy, r = 130*k, 45*k, 18*k
        self._oval(hx-r, hy-r, hx+r, hy+r, fill, outline)

    # ---------- movement (drag) ----------
    def _enable_drag(self, widget):
        # Allow dragging from canvas or window unless resizing is active.
        def start(e):
            if getattr(self, "_resize_active", False): return
            widget._drag = (e.x_root, e.y_root, self.mini_win.winfo_x(), self.mini_win.winfo_y())
        def drag(e):
            if getattr(self, "_resize_active", False) or not hasattr(widget, "_drag"): return
            x0, y0, wx, wy = widget._drag
            dx, dy = e.x_root - x0, e.y_root - y0
            self.mini_win.geometry(f"+{wx+dx}+{wy+dy}")
        widget.bind("<Button-1>", start)
        widget.bind("<B1-Motion>", drag)

    # ---------- edge/corner resize (uniform square) ----------
    def _install_resize_handlers(self):
        c = self.mini_canvas
        c.bind("<Motion>", self._on_mini_motion)
        c.bind("<ButtonPress-1>", self._on_mini_press)
        c.bind("<ButtonRelease-1>", self._on_mini_release)
        c.bind("<B1-Motion>", self._on_mini_drag)

    def _hit_test_edge(self, x, y, w, h):
        m = RESIZE_MARGIN
        left   = x <= m
        right  = x >= w - m
        top    = y <= m
        bottom = y >= h - m
        if top and left: return "nw"
        if top and right: return "ne"
        if bottom and left: return "sw"
        if bottom and right: return "se"
        if top: return "n"
        if bottom: return "s"
        if left: return "w"
        if right: return "e"
        return None

    def _cursor_for_edge(self, edge):
        # Cross-platform Tk cursor names
        return {
            "n": "top_side", "s": "bottom_side",
            "e": "right_side", "w": "left_side",
            "ne": "top_right_corner", "nw": "top_left_corner",
            "se": "bottom_right_corner", "sw": "bottom_left_corner"
        }.get(edge, "arrow")

    def _on_mini_motion(self, e):
        w, h = self.mini_canvas.winfo_width(), self.mini_canvas.winfo_height()
        edge = self._hit_test_edge(e.x, e.y, w, h)
        self._resize_edge = edge
        try: self.mini_canvas.config(cursor=self._cursor_for_edge(edge))
        except Exception: pass

    def _on_mini_press(self, e):
        # Decide edge at mouse down
        w, h = self.mini_canvas.winfo_width(), self.mini_canvas.winfo_height()
        self._resize_edge = self._hit_test_edge(e.x, e.y, w, h)
        if not self._resize_edge:
            self._resize_active = False
            self._press_info = None
            return
        self._resize_active = True
        self._press_info = (e.x_root, e.y_root,
                            self.mini_win.winfo_x(), self.mini_win.winfo_y(),
                            self.mini_size.get())

    def _on_mini_release(self, e):
        self._resize_active = False
        self._press_info = None

    def _on_mini_drag(self, e):
        if not self._resize_active or not self._press_info:
            return
        x0, y0, wx0, wy0, s0 = self._press_info
        dx, dy = e.x_root - x0, e.y_root - y0

        edge = self._resize_edge
        # Uniform square scaling
        sign_x = 1 if edge in ("e","ne","se") else (-1 if edge in ("w","nw","sw") else 0)
        sign_y = 1 if edge in ("s","se","sw") else (-1 if edge in ("n","ne","nw") else 0)
        delta = max(sign_x*dx, sign_y*dy) if (sign_x and sign_y) else (sign_x*dx or sign_y*dy)

        new_s = int(max(MIN_MINI_SIZE, min(MAX_MINI_SIZE, s0 + delta)))
        if new_s == self.mini_size.get():
            return

        # Keep grabbed edge anchored
        pos_x, pos_y = wx0, wy0
        if edge in ("w","nw","sw"):
            pos_x = wx0 + (s0 - new_s)
        if edge in ("n","ne","nw"):
            pos_y = wy0 + (s0 - new_s)

        self.mini_size.set(new_s)
        self.mini_win.geometry(f"{new_s}x{new_s}+{pos_x}+{pos_y}")
        self.mini_canvas.config(width=new_s, height=new_s)
        self._mini_draw_shape()
        self._mini_build_controls()
        self._mini_render()
        self._mini_update_buttons()

if __name__ == "__main__":
    app = TimerApp()
    app.mainloop()


