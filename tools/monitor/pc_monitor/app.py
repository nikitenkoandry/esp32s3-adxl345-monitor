"""Native Windows/Tk interface for the ADXL345 CSV firmware."""

from __future__ import annotations

import argparse
import math
import time
import tkinter as tk
from collections import deque
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from pc_monitor.orientation_view import OrientationPage

from pc_monitor.stream import (
    BAUD_RATE, SAMPLE_RATE, CsvRecorder, DemoWorker, Mailbox, Sample,
    SerialWorker, Stats, available_ports, peak_indices,
)

BG = "#0b1220"
PANEL = "#111d30"
PLOT = "#0e1829"
GRID = "#24334a"
TEXT = "#e4edf7"
MUTED = "#91a4bd"
BLUE = "#57b9ff"
GREEN = "#48d3a0"
ORANGE = "#ffa56d"
AXES = (("X", BLUE), ("Y", GREEN), ("Z", ORANGE))
G_TO_SI = 9.80665


def y_limits(values: list[float], factor: float, auto: bool) -> tuple[float, float]:
    if not auto:
        return -16 * factor, 16 * factor
    low, high = (min(values), max(values)) if values else (-1 * factor, 1 * factor)
    span = max(high - low, 0.2 * factor)
    center = (low + high) / 2
    low, high = center - span * 0.65, center + span * 0.65
    raw_step = (high - low) / 4
    power = 10 ** math.floor(math.log10(raw_step))
    step = next(n * power for n in (1, 2, 2.5, 5, 10) if n * power >= raw_step)
    return math.floor(low / step) * step, math.ceil(high / step) * step


class TraceCanvas(tk.Canvas):
    def __init__(self, parent, axis: str, color: str):
        super().__init__(parent, bg=PLOT, highlightthickness=0, height=165)
        self.axis, self.color = axis, color

    def draw(self, samples: list[Sample], seconds: float, factor: float, unit: str, auto: bool):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 150 or height < 60:
            return
        left, right, top, bottom = 68, width - 22, 24, height - 20
        plot_width, plot_height = right - left, bottom - top
        t_right = max(seconds, samples[-1].t) if samples else seconds
        t_left = t_right - seconds
        values = [getattr(s, self.axis.lower()) * factor for s in samples]
        y_min, y_max = y_limits(values, factor, auto)

        self.create_text(left, 12, anchor="w", text=f"{self.axis}  /  {unit}",
                         fill=self.color, font=("Segoe UI", 11, "bold"))
        tick_count = 5 if plot_height >= 100 else (3 if plot_height >= 35 else 2)
        for i in range(tick_count):
            y = top + i * plot_height / (tick_count - 1)
            value = y_max - i * (y_max - y_min) / (tick_count - 1)
            self.create_line(left, y, right, y, fill=GRID)
            self.create_text(left - 10, y, anchor="e", text=f"{value:.3g}",
                             fill=MUTED, font=("Segoe UI", 9))
        for i in range(6):
            x = left + i * plot_width / 5
            t = t_left + i * seconds / 5
            self.create_line(x, top, x, bottom, fill=GRID)
            self.create_text(x, bottom + 11, text=f"{t:.1f}", fill=MUTED, font=("Segoe UI", 9))
        self.create_text(right, 14, anchor="e", text="Time, s", fill=MUTED, font=("Segoe UI", 9))

        if not samples:
            self.create_text((left + right) / 2, (top + bottom) / 2,
                             text="Connect ESP32-S3 or start the demo", fill=MUTED,
                             font=("Segoe UI", 11))
            return

        # Break curves across known discontinuities; never join opposite sides of a gap.
        begin = 0
        segments = []
        for i in range(1, len(samples)):
            if samples[i].gap_before or samples[i].index != samples[i - 1].index + 1:
                segments.append((begin, i))
                begin = i
        segments.append((begin, len(samples)))
        for begin, end in segments:
            indices = peak_indices(values[begin:end], max(1, int(plot_width)))
            coords = []
            for local in indices:
                i = begin + local
                x = left + (samples[i].t - t_left) * plot_width / seconds
                y = bottom - (values[i] - y_min) * plot_height / (y_max - y_min)
                # Fixed range may clip overrange values; keep drawing inside the plot.
                y = min(bottom, max(top, y))
                coords.extend((x, y))
            if len(coords) >= 4:
                self.create_line(*coords, fill=self.color, width=1.4)
            elif coords:
                x, y = coords
                self.create_oval(x - 2, y - 2, x + 2, y + 2, fill=self.color, outline="")


class MonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ADXL345 — Acceleration Monitor")
        self.configure(bg=BG)
        width = min(1180, self.winfo_screenwidth() - 70)
        height = min(890, self.winfo_screenheight() - 90)
        self.geometry(f"{width}x{height}+35+25")
        self.minsize(900, 680)
        self._icon = tk.PhotoImage(width=32, height=32)
        self._icon.put(BG, to=(0, 0, 32, 32))
        for x in range(2, 30):
            y = 16 - int(8 * math.sin(x * 0.45))
            self._icon.put(BLUE, to=(x, y, x + 1, y + 3))
        self.iconphoto(True, self._icon)

        self.mailbox, self.recorder = Mailbox(), CsvRecorder()
        self.worker: SerialWorker | DemoWorker | None = None
        self.source = ""
        self.connected = self.stopping = self.closing = False
        self.last_error = ""
        self.history: deque[Sample] = deque(maxlen=int(SAMPLE_RATE * 60) + 16)
        self.frozen: list[Sample] | None = None
        self.dirty = True
        self.rate = 0.0
        self.rate_time, self.rate_count = time.monotonic(), 0
        self.stats = Stats(0, 0, 0, 0, 0)
        self.port_names: dict[str, str] = {}
        self._style()
        self._build()
        self.refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(40, self.poll)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TButton", background="#243650", foreground=TEXT,
                        borderwidth=0, padding=(13, 8), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#334d70"), ("disabled", "#18253a")],
                  foreground=[("disabled", "#61748d")])
        style.configure("Accent.TButton", background="#1767a1")
        style.map("Accent.TButton", background=[("active", "#2383c6"), ("disabled", "#182b41")])
        style.configure("TCombobox", fieldbackground="#17253b", background="#243650",
                        foreground=TEXT, arrowcolor=TEXT, padding=6, borderwidth=0)
        style.map("TCombobox", fieldbackground=[("readonly", "#17253b"), ("disabled", "#152033")],
                  foreground=[("readonly", TEXT), ("disabled", "#61748d")])
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#17253b", foreground=MUTED,
                        padding=(16, 8), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#243650")],
                  foreground=[("selected", TEXT)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", "#1767a1")

    def _build(self):
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        heading = ttk.Frame(outer)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(heading, text="Acceleration Monitor", font=("Segoe UI", 21, "bold")).pack(side="left")
        ttk.Label(heading, text="ADXL345  /  USB  /  800 Hz", style="Muted.TLabel").pack(side="left", padx=18)
        self.state_label = ttk.Label(heading, text="● Disconnected", foreground=MUTED)
        self.state_label.pack(side="right")

        controls = ttk.Frame(outer, style="Panel.TFrame", padding=12)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, text="USB / COM port", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(controls, text="Baud rate", style="Panel.TLabel").grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(controls, textvariable=self.port_var, width=40)
        self.port_combo.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.refresh_button = ttk.Button(controls, text="↻", width=3, command=self.refresh_ports)
        self.refresh_button.grid(row=1, column=1, padx=(7, 0), pady=(5, 0))
        self.baud_var = tk.StringVar(value=str(BAUD_RATE))
        self.baud_combo = ttk.Combobox(controls, textvariable=self.baud_var, state="readonly", width=10,
                                       values=("115200", "230400", "460800", "921600"))
        self.baud_combo.grid(row=1, column=2, padx=12, pady=(5, 0))
        self.connect_button = ttk.Button(controls, text="Connect", style="Accent.TButton", command=self.connect)
        self.connect_button.grid(row=1, column=3, pady=(5, 0))
        self.demo_button = ttk.Button(controls, text="Demo", command=self.demo)
        self.demo_button.grid(row=1, column=4, padx=(8, 0), pady=(5, 0))

        self.pages = ttk.Notebook(outer)
        self.pages.grid(row=2, column=0, sticky="nsew")
        self.graphs_page = ttk.Frame(self.pages, padding=(0, 10, 0, 0))
        self.graphs_page.columnconfigure(0, weight=1)
        self.graphs_page.rowconfigure(2, weight=1)
        self.pages.add(self.graphs_page, text="XYZ Graphs")
        self.orientation_page = OrientationPage(self.pages, self.mark_dirty)
        self.pages.add(self.orientation_page, text="3D Orientation")
        self.pages.bind("<<NotebookTabChanged>>", lambda _: self.mark_dirty())

        settings = ttk.Frame(self.graphs_page)
        settings.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(settings, text="History:").pack(side="left")
        self.seconds_var = tk.StringVar(value="5")
        seconds_combo = ttk.Combobox(settings, state="readonly", width=4, textvariable=self.seconds_var,
                                     values=("2", "5", "10", "30", "60"))
        seconds_combo.pack(side="left", padx=(5, 4))
        seconds_combo.bind("<<ComboboxSelected>>", lambda _: self.mark_dirty())
        ttk.Label(settings, text="s     Units:").pack(side="left")
        self.unit_var = tk.StringVar(value="g")
        unit_combo = ttk.Combobox(settings, state="readonly", width=6, textvariable=self.unit_var,
                                  values=("g", "m/s²"))
        unit_combo.pack(side="left", padx=(5, 14))
        unit_combo.bind("<<ComboboxSelected>>", lambda _: self.mark_dirty())
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings, text="Auto-scale Y", variable=self.auto_var,
                         command=self.mark_dirty).pack(side="left")
        self.record_button = ttk.Button(settings, text="Record CSV", command=self.toggle_recording)
        self.record_button.pack(side="right")
        self.pause_button = ttk.Button(settings, text="Pause graphs", command=self.pause)
        self.pause_button.pack(side="right", padx=8)

        cards = ttk.Frame(self.graphs_page)
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.value_vars = []
        for i, (axis, color) in enumerate(AXES):
            cards.columnconfigure(i, weight=1, uniform="axis")
            card = ttk.Frame(cards, style="Panel.TFrame", padding=(14, 8))
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 0 if i == 2 else 5))
            ttk.Label(card, text=axis, foreground=color, background=PANEL,
                      font=("Segoe UI", 14, "bold")).pack(side="left", padx=(0, 12))
            value = tk.StringVar(value="— g")
            self.value_vars.append(value)
            ttk.Label(card, textvariable=value, background=PANEL, foreground=TEXT,
                      font=("Consolas", 22, "bold")).pack(side="left")

        graphs = ttk.Frame(self.graphs_page)
        graphs.grid(row=2, column=0, sticky="nsew")
        graphs.columnconfigure(0, weight=1)
        self.canvases = []
        for i, (axis, color) in enumerate(AXES):
            graphs.rowconfigure(i, weight=1, uniform="plot")
            canvas = TraceCanvas(graphs, axis, color)
            canvas.grid(row=i, column=0, sticky="nsew", pady=(0, 7 if i < 2 else 0))
            canvas.bind("<Configure>", lambda _: self.mark_dirty())
            self.canvases.append(canvas)

        footer = ttk.Frame(outer)
        footer.grid(row=3, column=0, sticky="ew", pady=(10, 5))
        self.stats_var = tk.StringVar(value="Samples: 0   •   Rate: 0 samples/s")
        ttk.Label(footer, textvariable=self.stats_var, style="Muted.TLabel").pack(side="left")
        self.record_var = tk.StringVar(value="Nominal 800 Hz time · acceleration includes gravity")
        ttk.Label(footer, textvariable=self.record_var, style="Muted.TLabel").pack(side="right")
        self.log = tk.Text(outer, height=3, bg=PLOT, fg=MUTED, relief="flat", borderwidth=0,
                           padx=10, pady=7, font=("Consolas", 9), wrap="word", state="disabled")
        self.log.grid(row=4, column=0, sticky="ew")
        self.log.tag_configure("error", foreground="#ff8080")
        self.log.tag_configure("device_warning", foreground=ORANGE)
        self.log.tag_configure("connected", foreground=GREEN)
        self._log("info", "Ready. Close Arduino Serial Monitor before connecting to the COM port.")
        self._controls()

    def mark_dirty(self):
        self.dirty = True

    def _log(self, level: str, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", f"{datetime.now():%H:%M:%S}  {text}\n", level)
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 200:
            self.log.delete("1.0", f"{lines - 200}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_ports(self):
        if self.worker is not None:
            return
        old = self.port_var.get()
        try:
            ports = available_ports()
        except ImportError:
            ports = []
            self._log("error", "USB requires pyserial. Run Install_Dependencies.cmd or use the packaged EXE.")
        except Exception as exc:
            ports = []
            self._log("error", f"Could not list serial ports: {exc}")
        self.port_names = {f"{port} — {description}": port for port, description in ports}
        self.port_combo.configure(values=list(self.port_names))
        if old in self.port_names:
            self.port_var.set(old)
        elif self.port_names:
            # Prefer the USB adapter instead of Windows' built-in COM/Bluetooth ports.
            preferred = next((name for name in self.port_names
                              if any(word in name.lower() for word in ("usb", "ch34", "cp210", "ftdi", "esp32"))),
                             next(iter(self.port_names)))
            self.port_var.set(preferred)
        else:
            self.port_var.set("")

    def _controls(self):
        busy = self.worker is not None
        self.port_combo.configure(state="disabled" if busy else "normal")
        self.baud_combo.configure(state="disabled" if busy else "readonly")
        self.refresh_button.configure(state="disabled" if busy else "normal")
        self.connect_button.configure(
            text="Disconnect" if busy and self.source == "serial" else "Connect",
            state="disabled" if self.stopping or (busy and self.source == "demo") else "normal")
        self.demo_button.configure(
            text="Stop demo" if busy and self.source == "demo" else "Demo",
            state="disabled" if self.stopping or (busy and self.source == "serial") else "normal")
        self.record_button.configure(state="normal" if busy and not self.stopping else "disabled")

    def connect(self):
        if self.worker is not None:
            self.disconnect()
            return
        selected = self.port_var.get().strip()
        port = self.port_names.get(selected, selected)
        if not port:
            messagebox.showinfo("COM port", "Connect ESP32-S3 via USB and select its COM port.", parent=self)
            return
        self._start(SerialWorker(port, int(self.baud_var.get()), self.mailbox, self.recorder), "serial")

    def demo(self):
        if self.worker is not None:
            self.disconnect()
            return
        self._start(DemoWorker(self.mailbox, self.recorder), "demo")

    def _start(self, worker, source: str):
        self.mailbox.reset()
        self.history.clear()
        self.orientation_page.reset()
        self.frozen = None
        self.pause_button.configure(text="Pause graphs")
        self.connected, self.stopping, self.last_error = False, False, ""
        self.stats = Stats(0, 0, 0, 0, 0)
        self.rate, self.rate_count, self.rate_time = 0, 0, time.monotonic()
        self.source, self.worker, self.dirty = source, worker, True
        self.state_label.configure(text="● Connecting…", foreground=ORANGE)
        worker.start()
        self._controls()

    def disconnect(self):
        if self.worker is not None:
            self.stopping = True
            self.worker.stop_event.set()
            self.state_label.configure(text="● Stopping…", foreground=ORANGE)
            self._controls()

    def pause(self):
        if self.frozen is None:
            self.frozen = list(self.history)
            self.pause_button.configure(text="Resume graphs")
            self._log("info", "Graphs paused. Data reception and CSV recording continue.")
        else:
            self.frozen = None
            self.pause_button.configure(text="Pause graphs")
        self.dirty = True

    def toggle_recording(self):
        if self.recorder.active:
            self.stop_recording()
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Save acceleration stream", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile=f"ADXL345_{datetime.now():%Y%m%d_%H%M%S}.csv")
        if path:
            try:
                self.recorder.start(path)
                self._log("info", f"Recording CSV: {path}")
            except (OSError, RuntimeError) as exc:
                messagebox.showerror("CSV recording", str(exc), parent=self)

    def stop_recording(self):
        if self.recorder.active:
            rows = self.recorder.rows
            try:
                self.recorder.stop()
                self._log("info", f"CSV saved: {rows} samples.")
            except OSError as exc:
                self._log("error", f"Could not save CSV: {exc}")

    def draw(self):
        self.dirty = False
        if self.pages.select() == str(self.orientation_page):
            fresh = self.connected and time.monotonic() - self.stats.last_rx <= 2
            self.orientation_page.draw(fresh=fresh)
            return
        data = self.frozen if self.frozen is not None else list(self.history)
        seconds = float(self.seconds_var.get())
        factor = 1.0 if self.unit_var.get() == "g" else G_TO_SI
        unit = self.unit_var.get()
        if data:
            left = max(seconds, data[-1].t) - seconds
            first = 0
            while first + 1 < len(data) and data[first + 1].t < left:
                first += 1
            data = data[first:]
            if data and data[0].t < left:
                data = data[1:]
        for canvas in self.canvases:
            canvas.draw(data, seconds, factor, unit, self.auto_var.get())
        for i, (axis, _) in enumerate(AXES):
            value = getattr(data[-1], axis.lower()) * factor if data else None
            self.value_vars[i].set(f"{value:+.4f} {unit}" if value is not None else f"— {unit}")

    def poll(self):
        if self.closing:
            return
        frame_started = time.perf_counter()
        samples, events, self.stats = self.mailbox.take()
        if samples:
            self.history.extend(samples)
            self.orientation_page.ingest(samples)
            if self.frozen is None:
                self.dirty = True
        for event in events:
            self._log(event.level, event.text)
            if event.level == "connected":
                self.connected = True
            elif event.level == "error":
                self.last_error = event.text
            elif event.level == "disconnected":
                self.connected = False
        if self.worker is not None and not self.worker.is_alive():
            self.worker = None
            self.connected = self.stopping = False
            self.stop_recording()
            self._controls()

        now = time.monotonic()
        if now - self.rate_time >= 1:
            self.rate = (self.stats.received - self.rate_count) / (now - self.rate_time)
            self.rate_time, self.rate_count = now, self.stats.received
        if self.worker is None:
            self.state_label.configure(text="● Connection error" if self.last_error else "● Disconnected",
                                       foreground=ORANGE if self.last_error else MUTED)
        elif self.connected and not self.stopping:
            if not self.stats.last_rx or now - self.stats.last_rx > 2:
                self.state_label.configure(text="● Waiting for data…", foreground=ORANGE)
            else:
                label = "DEMO" if self.source == "demo" else "Connected"
                if self.frozen is not None:
                    label += " · graphs paused"
                self.state_label.configure(text=f"● {label}", foreground=GREEN)

        self.stats_var.set(
            f"Samples: {self.stats.received:,}   •   Rate: {self.rate:.0f} samples/s   •   "
            f"Bad lines: {self.stats.invalid}   •   Warnings: {self.stats.device_warnings}   •   "
            f"UI dropped: {self.stats.display_dropped}")
        recording = self.recorder.active
        self.record_button.configure(text="■ Stop CSV" if recording else "Record CSV")
        if recording:
            self.record_var.set(f"● CSV: {self.recorder.rows:,} rows")
        elif self.stats.irq is not None:
            irq = self.stats.irq
            self.record_var.set(f"INT1: {irq['irq_edges']:,} · FIFO: {irq['fifo_full']} · "
                                f"dropped: {irq['queue_dropped']} · timeouts: {irq['timeouts']}")
        else:
            self.record_var.set("Nominal 800 Hz time · acceleration includes gravity")
        if self.pages.select() == str(self.orientation_page):
            self.dirty = True  # Also refresh stale/paused status when data stops.
        if self.dirty:
            self.draw()
        # Include drawing time in the frame budget rather than adding it to each
        # interval. The 3D page targets 50 FPS; the history plots target 25 FPS.
        frame_ms = 20 if self.pages.select() == str(self.orientation_page) else 40
        elapsed_ms = (time.perf_counter() - frame_started) * 1000
        self.after(max(1, round(frame_ms - elapsed_ms)), self.poll)

    def close(self):
        if self.closing:
            return
        self.closing = True
        if self.worker is not None:
            self.worker.stop_event.set()
        self._close_deadline = time.monotonic() + 3
        self.after(20, self._finish_close)

    def _finish_close(self):
        if self.worker is not None and self.worker.is_alive() and time.monotonic() < self._close_deadline:
            self.after(30, self._finish_close)
            return
        self.stop_recording()
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description="ADXL345 USB acceleration monitor")
    parser.add_argument("--demo", action="store_true", help="Start the synthetic 800 Hz signal")
    parser.add_argument("--port", help="Connect to a COM port on startup, e.g. COM5")
    parser.add_argument("--baud", type=int, default=BAUD_RATE)
    parser.add_argument("--orientation", action="store_true", help="Open the 3D tilt page")
    args = parser.parse_args()
    app = MonitorApp()
    if args.orientation:
        app.pages.select(app.orientation_page)
    if args.demo:
        app.after(100, app.demo)
    elif args.port:
        app.port_var.set(args.port)
        app.baud_var.set(str(args.baud))
        app.after(100, app.connect)
    app.mainloop()


if __name__ == "__main__":
    main()
