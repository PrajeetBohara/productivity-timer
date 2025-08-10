# file: tiny_timer_mini_edge_resize_full.py
import tkinter as tk
from tkinter import ttk, messagebox
import time, math, sys, os, shutil, subprocess
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

class TimerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tiny Timer + Productivity")
        self.geometry("430x310")
        self.minsize(360, 260)
        self.attributes("-topmost", True)

        # ---- timer state ----
        self.state = "idle"
        self.total_seconds = 0
        self.remaining_seconds = 0
        self.end_at_ms = 0
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
        self.mini_win = None
        self.mini_shape = tk.StringVar(value="fighter")  # default mini shape
        self.mini_size = tk.IntVar(value=220)            # square size (uniform)
        self.mini_bg_trans = "magenta"

        # mini drag/resize internals
        self._resize_edge = None       # 'n','s','e','w','ne','nw','se','sw'
        self._resize_active = False
        self._press_info = None        # (x_root, y_root, win_x, win_y, size_at_press)

        self._build_ui()
        self._apply_compact()
        self._set_buttons()
        self._render(0)
        self._update_today_label()

        self.bind("<Return>", lambda e: self.on_start() if self.state == "idle" else None)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- Main UI ----------
    def _build_ui(self):
        root = ttk.Frame(self, padding=(10, 8))
        root.pack(fill="both", expand=True)

        title_row = ttk.Frame(root); title_row.pack(fill="x")
        ttk.Label(title_row, text="Tiny Timer", font=("Segoe UI", 14, "bold")).pack(side="left")
        self.chk_top = ttk.Checkbutton(title_row, text="Always on top",
                                       variable=self.topmost_var, command=self._toggle_topmost)
        self.chk_top.pack(side="right")

        ctrl_row = ttk.Frame(root); ctrl_row.pack(fill="x", pady=(4, 0))
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
        ttk.Button(mini_frame, text="Open Mini", command=self.open_mini).pack(side="left", padx=6)

        # inputs
        self.inputs_wrap = ttk.Frame(root); self.inputs_wrap.pack(fill="x", pady=(6, 0))
        self.var_h = tk.StringVar(value="0")
        self.var_m = tk.StringVar(value="25")
        self.var_s = tk.StringVar(value="0")
        self._add_number_field(self.inputs_wrap, "Hrs", self.var_h, 0, 0, 0, 99)
        self._add_number_field(self.inputs_wrap, "Min", self.var_m, 0, 1, 0, 59)
        self._add_number_field(self.inputs_wrap, "Sec", self.var_s, 0, 2, 0, 59)

        # display + progress
        self.lbl_time = ttk.Label(root, text="00:00:00", font=("Consolas", 36, "bold"), anchor="center")
        self.lbl_time.pack(pady=(10, 4), fill="x")
        self.progress = ttk.Progressbar(root, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x")

        # productivity
        self.prod_row = ttk.Frame(root); self.prod_row.pack(fill="x", pady=(8, 0))
        self.chk_track = ttk.Checkbutton(self.prod_row, text="Track Productivity (adds while running)",
                                         variable=self.track_var)
        self.chk_track.pack(side="left")
        self.lbl_today = ttk.Label(self.prod_row, text="Today: 00:00:00", font=("Segoe UI", 10, "bold"))
        self.lbl_today.pack(side="left", padx=10)
        self.btn_reset_tracked = ttk.Button(self.prod_row, text="Reset Tracked",
                                            command=self.on_reset_tracked, width=12)
        self.btn_reset_tracked.pack(side="right")

        # status + controls
        self.var_msg = tk.StringVar(value="")
        ttk.Label(root, textvariable=self.var_msg, foreground="#6b7280").pack(pady=(6, 0))
        btns = ttk.Frame(root); btns.pack(pady=(8, 0))
        self.btn_start  = ttk.Button(btns, text="Start",  width=8, command=self.on_start)
        self.btn_pause  = ttk.Button(btns, text="Pause",  width=8, command=self.on_pause)
        self.btn_resume = ttk.Button(btns, text="Resume", width=8, command=self.on_resume)
        self.btn_stop   = ttk.Button(btns, text="Stop",   width=8, command=self.on_stop)
        for i, b in enumerate((self.btn_start,self.btn_pause,self.btn_resume,self.btn_stop)):
            b.grid(row=0, column=i, padx=6)

        try:
            self.call("source", "sun-valley.tcl"); self.call("set_theme", "dark")
        except tk.TclError:
            pass

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
            self.inputs_wrap.forget(); self.prod_row.forget()
            self.geometry("320x180")
            self.lbl_time.configure(font=("Consolas", 30, "bold"))
        else:
            self.inputs_wrap.pack(fill="x", pady=(6, 0))
            self.prod_row.pack(fill="x", pady=(8, 0))
            self.geometry("430x310")
            self.lbl_time.configure(font=("Consolas", 36, "bold"))

    def _toggle_topmost(self):
        self.attributes("-topmost", self.topmost_var.get())

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

    # ---------- Timer controls ----------
    def on_start(self):
        if self.state != "idle": return
        self.total_seconds = self._calc_total_seconds()
        if self.total_seconds <= 0:
            messagebox.showwarning("Invalid time","Please enter a time greater than 0 seconds."); return
        self.remaining_seconds = self.total_seconds
        self.end_at_ms = self._now_ms() + self.remaining_seconds*1000
        self.last_tick_ms = self._now_ms()
        self.state = "running"; self._set_buttons(); self._set_inputs_enabled(False)
        self._set_msg("Timer started."); self._tick()

    def on_pause(self):
        if self.state != "running": return
        self._apply_productivity_delta()
        self.remaining_seconds = max(0, math.ceil((self.end_at_ms - self._now_ms())/1000))
        self._cancel_tick(); self.state = "paused"; self._set_buttons(); self._set_msg("Paused.")

    def on_resume(self):
        if self.state != "paused": return
        if self.remaining_seconds <= 0: return
        self.end_at_ms = self._now_ms() + self.remaining_seconds*1000
        self.last_tick_ms = self._now_ms()
        self.state = "running"; self._set_buttons(); self._set_msg("Resumed."); self._tick()

    def on_stop(self):
        self._apply_productivity_delta()
        self._cancel_tick(); self.state = "idle"
        self.total_seconds = 0; self.remaining_seconds = 0
        self._render(0); self._set_buttons(); self._set_inputs_enabled(True); self._set_msg("Stopped.")

    def on_reset_tracked(self):
        self.productive_ms_today = 0; self._update_today_label(); self._set_msg("Tracked time reset to 0.")

    # ---------- Tick / Productivity ----------
    def _tick(self):
        now = self._now_ms()
        if self._today_key() != self.current_day:
            self.current_day = self._today_key()
            self.productive_ms_today = 0
            self._update_today_label()

        left = max(0, math.ceil((self.end_at_ms - now)/1000))
        self.remaining_seconds = left
        self._render(left)

        if self.state == "running" and self.track_var.get() and self.last_tick_ms is not None:
            delta = max(0, now - self.last_tick_ms)
            self.productive_ms_today += delta
            self._update_today_label()
        self.last_tick_ms = now

        if left <= 0:
            self.state = "idle"; self._set_buttons(); self._set_inputs_enabled(True)
            self._set_msg("Time's up!")
            self._play_alarm()   # <-- play custom audio (with fallback)
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
        pct = 0 if self.total_seconds <= 0 else (1 - seconds_left/self.total_seconds)*100
        self.progress["value"] = max(0, min(100, pct))
        if self.mini_win and self.mini_win.winfo_exists(): self._mini_render()

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

    def _set_msg(self, text): self.var_msg.set(text or "")
    def _update_today_label(self):
        s = round(self.productive_ms_today/1000)
        self.lbl_today.config(text=f"Today: {s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}")
        # (mini is minimal; omit total display there)

    def _today_key(self): return datetime.now().strftime("%Y-%m-%d")
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
        if self.state == "idle": self._render(self._calc_total_seconds()); self._set_msg("")
    def _on_close(self):
        self._cancel_tick()
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


