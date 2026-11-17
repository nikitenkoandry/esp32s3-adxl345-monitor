"""A software-rendered 3D tilt example using the same live serial stream."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from pc_monitor.orientation import Matrix, TiltEstimator, TiltState, angle_between, transform

BG, PANEL, PLOT = "#0b1220", "#111d30", "#0e1829"
TEXT, MUTED = "#e4edf7", "#91a4bd"
BLUE, GREEN, ORANGE = "#57b9ff", "#48d3a0", "#ffa56d"


class PoseCanvas(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg=PLOT, highlightthickness=0, width=640, height=390)

    def draw(self, state: TiltState, reference: Matrix | None):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 100 or height < 100:
            return
        scale = min(width / 6.0, height / 3.8)
        cx, cy = width * 0.5, height * 0.53
        azimuth, elevation = math.radians(-35), math.radians(36)
        ca, sa, ce, se = math.cos(azimuth), math.sin(azimuth), math.cos(elevation), math.sin(elevation)

        def project(p):
            x, y, z = p
            return (cx + scale * (ca * x + sa * y),
                    cy - scale * (-sa * se * x + ca * se * y + ce * z),
                    sa * ce * x - ca * ce * y + se * z)

        def line(a, b, **kwargs):
            pa, pb = project(a), project(b)
            self.create_line(pa[0], pa[1], pb[0], pb[1], **kwargs)

        for i in range(-6, 7):
            coordinate = i * 0.5
            line((coordinate, -3, -1.9), (coordinate, 3, -1.9), fill="#22324a")
            line((-3, coordinate, -1.9), (3, coordinate, -1.9), fill="#22324a")
        line((-2.5, -1.7, -1.9), (-2.5, -1.7, 0.2), fill=MUTED, arrow="last", width=1.5)
        px, py, _ = project((-2.5, -1.7, 0.5))
        self.create_text(px, py, text="Vertical", fill=MUTED, font=("Segoe UI", 9))

        if state.matrix is None:
            self.create_text(width / 2, height * 0.43,
                             text="Waiting for gravity direction" if state.quality == "waiting" else "No reliable pose",
                             fill=MUTED, font=("Segoe UI", 15, "bold"))
            return

        def box(x1, x2, y1, y2, z1, z2):
            return [(x1, y1, z1), (x2, y1, z1), (x2, y2, z1), (x1, y2, z1),
                    (x1, y1, z2), (x2, y1, z2), (x2, y2, z2), (x1, y2, z2)]

        board = box(-1.4, 1.4, -0.9, 0.9, -0.10, 0.10)
        faces = [(0, 1, 2, 3), (0, 1, 5, 4), (1, 2, 6, 5),
                 (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
                 (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        if reference is not None:
            ref = [transform(reference, point) for point in board]
            for a, b in edges:
                line(ref[a], ref[b], fill="#71819a", dash=(4, 4), width=1)

        polygons = []
        held = state.quality in ("undefined", "dynamic")
        palette = ("#152b32", "#24564f", "#1e4844", "#20453e", "#286151", "#267b66")
        if held:
            palette = ("#26323a", "#394a53", "#31454d", "#35454a", "#45565b", "#4a6568")

        def add_box(vertices, colors, outline):
            world = [project(transform(state.matrix, point)) for point in vertices]
            for face, color in zip(faces, colors):
                points = [world[i] for i in face]
                polygons.append((sum(p[2] for p in points) / 4,
                                 [v for p in points for v in p[:2]], color, outline))

        add_box(board, palette, "#508e84" if not held else "#71818c")
        add_box(box(-0.48, 0.48, -0.36, 0.36, 0.11, 0.31),
                ("#111c2a", "#172438", "#24354c", "#192b40", "#2b3a4e", "#324761"), "#69809b")
        for y in (-0.67, 0.67):
            for x in (-1.1, -0.65, 0.65, 1.1):
                add_box(box(x - 0.09, x + 0.09, y - 0.09, y + 0.09, 0.105, 0.13),
                        ("#785b2d",) * 5 + ("#d5ad61",), "#bc9854")
        for _, points, color, outline in sorted(polygons, key=lambda p: p[0]):
            self.create_polygon(*points, fill=color, outline=outline, width=1)

        origin = (0.0, 0.0, 0.4)
        for label, endpoint, color in (("+X", (1.7, 0, 0.4), BLUE),
                                       ("+Y", (0, 1.6, 0.4), GREEN),
                                       ("+Z", (0, 0, 1.6), ORANGE)):
            a, b = transform(state.matrix, origin), transform(state.matrix, endpoint)
            line(a, b, fill=color, width=2, arrow="last")
            x, y, _ = project(b)
            self.create_text(x + 10, y - 9, text=label, fill=color, font=("Segoe UI", 10, "bold"))
        self.create_text(16, height - 35, anchor="w", text="Sensor axes:  X     Y     Z",
                         fill=MUTED, font=("Segoe UI", 10))
        self.create_text(16, height - 15, anchor="w", text="Heading about vertical is not measured",
                         fill=ORANGE, font=("Segoe UI", 10))


class OrientationPage(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent, padding=(0, 10, 0, 0))
        self.on_change = on_change
        self.estimator = TiltEstimator()
        self.reference_g = self.reference_matrix = None
        self.frozen: TiltState | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 9))
        ttk.Label(toolbar, text="Slowly tilt the sensor about X and Y.",
                  foreground=TEXT).pack(side="left")
        self.pause_button = ttk.Button(toolbar, text="Pause model", command=self.pause)
        self.pause_button.pack(side="right")
        self.model = PoseCanvas(self)
        self.model.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        self.model.bind("<Configure>", lambda _: self.on_change())

        sidebar = ttk.Frame(self, style="Panel.TFrame", padding=14)
        sidebar.grid(row=1, column=1, sticky="ns")
        sidebar.columnconfigure(0, weight=1, minsize=130)
        sidebar.columnconfigure(1, weight=1, minsize=130)
        ttk.Label(sidebar, text="Gravity-based tilt", background=PANEL,
                  font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.values = {}
        for row, (key, label, color) in enumerate((
                ("roll", "Roll X", BLUE), ("pitch", "Pitch Y", GREEN),
                ("tilt", "Z from vertical", ORANGE)), start=1):
            card = ttk.Frame(sidebar, style="Panel.TFrame")
            card.grid(row=1 if row < 3 else 2, column=1 if row == 2 else 0,
                      sticky="nw", padx=(0, 9), pady=(0, 9))
            ttk.Label(card, text=label, background=PANEL, foreground=MUTED).pack(anchor="w")
            variable = tk.StringVar(value="—°")
            self.values[key] = variable
            ttk.Label(card, textvariable=variable, background=PANEL, foreground=color,
                      font=("Consolas", 19, "bold")).pack(anchor="w")
        metrics = ttk.Frame(sidebar, style="Panel.TFrame")
        metrics.grid(row=2, column=1, sticky="nw")
        self.norm_var = tk.StringVar(value="|a|: — g")
        ttk.Label(metrics, textvariable=self.norm_var, background=PANEL).pack(anchor="w", pady=(0, 7))
        self.delta_var = tk.StringVar(value="From reference: —")
        ttk.Label(metrics, textvariable=self.delta_var, background=PANEL, wraplength=135).pack(anchor="w")
        sidebar.rowconfigure(3, weight=1)

        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(9, 4))
        ttk.Label(actions, text="Smoothing, s:", foreground=MUTED).pack(side="left")
        self.tau_var = tk.StringVar(value="0.25")
        smoothing = ttk.Combobox(actions, state="readonly", textvariable=self.tau_var,
                                 values=("0.08", "0.25", "0.50", "1.00"), width=9)
        smoothing.pack(side="left", padx=(8, 18))
        smoothing.bind("<<ComboboxSelected>>", self.change_smoothing)
        self.reference_button = ttk.Button(actions, text="Set reference", command=self.remember)
        self.reference_button.pack(side="left")
        self.clear_button = ttk.Button(actions, text="Clear reference", command=self.clear_reference)
        self.clear_button.pack(side="left", padx=8)

        self.quality_label = ttk.Label(self, text="Waiting for data", foreground=MUTED)
        self.quality_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 4))
        self.hint_label = ttk.Label(
            self, text="The demo shows gentle tilts. This sensor cannot determine XYZ displacement or heading (yaw).",
            foreground=MUTED, wraplength=1050)
        self.hint_label.grid(row=4, column=0, columnspan=2, sticky="w")
        self.bind("<Configure>", self.resize_hint)

    def resize_hint(self, event):
        self.hint_label.configure(wraplength=max(300, event.width - 8))

    def reset(self):
        self.estimator.reset()
        self.frozen = None
        self.reference_g = self.reference_matrix = None
        self.pause_button.configure(text="Pause model")

    def ingest(self, samples):
        for sample in samples:
            self.estimator.update(sample)

    def change_smoothing(self, _=None):
        self.estimator.tau = float(self.tau_var.get())
        self.on_change()

    def pause(self):
        if self.frozen is None:
            self.frozen = self.estimator.snapshot()
            self.pause_button.configure(text="Resume model")
        else:
            self.frozen = None
            self.pause_button.configure(text="Pause model")
        self.on_change()

    def remember(self):
        state = self.frozen or self.estimator.snapshot()
        if state.unit_g is not None and state.quality == "gravity":
            self.reference_g, self.reference_matrix = state.unit_g, state.matrix
            self.on_change()

    def clear_reference(self):
        self.reference_g = self.reference_matrix = None
        self.on_change()

    def draw(self, *, fresh: bool):
        state = self.frozen or self.estimator.snapshot()
        self.model.draw(state, self.reference_matrix)
        approximate = state.quality == "dynamic"
        for key, value in (("roll", state.roll_deg), ("pitch", state.pitch_deg), ("tilt", state.tilt_deg)):
            self.values[key].set(f"{'≈' if approximate else ''}{value:+.1f}°" if value is not None else "—°")
        self.norm_var.set(f"|a|: {state.magnitude_g:.3f} g" if state.quality != "waiting" else "|a|: — g")
        if self.reference_g is not None and state.unit_g is not None and state.quality != "undefined":
            self.delta_var.set(f"From reference: {'≈' if approximate else ''}{angle_between(self.reference_g, state.unit_g):.1f}°")
        else:
            self.delta_var.set("From reference: —")
        self.reference_button.configure(state="normal" if fresh and state.quality == "gravity" else "disabled")
        self.clear_button.configure(state="normal" if self.reference_g is not None else "disabled")
        if state.quality == "waiting":
            text, color = "Waiting for data · connect a COM port or start Demo", MUTED
        elif self.frozen is not None:
            text, color = "Model paused · data reception continues", BLUE
        elif not fresh:
            text, color = "No fresh data · showing the last pose estimate", ORANGE
        elif state.quality == "undefined":
            text, color = "Gravity direction undefined · tilt estimate unavailable", ORANGE
        elif state.quality == "dynamic":
            text, color = "Acceleration or fast tilt · angle estimates may be distorted", ORANGE
        elif not state.roll_defined:
            text, color = "X axis is vertical · roll is undefined in this pose", ORANGE
        else:
            text, color = "Gravity-based estimate · best when stationary or tilting slowly", GREEN
        self.quality_label.configure(text=text, foreground=color)
