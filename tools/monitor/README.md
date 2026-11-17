# Desktop acceleration monitor

An English Python/Tk application for the ESP32-S3 ADXL345 CSV stream. This folder
contains the monitor sources, local setup/build/launch scripts, automated tests,
and an optional real-board verification utility. It can be used independently
of the firmware build environment.

## Install and run on Windows

Install Python 3.10+ with Tkinter and a working `python` command. From this folder:

```powershell
.\scripts\Install_Dependencies.cmd
.\scripts\Start_Monitor.cmd
# Synthetic 3D example without a board:
.\scripts\Start_3D_Demo.cmd
# Explicit real-board connection:
.\scripts\Start_Monitor.cmd --port COM16 --orientation
```

The installer creates a local `.venv/` and installs pySerial 3.5. Tkinter normally
comes with Python for Windows. Native USB/USB-UART drivers must be available.
Select the board's COM port and **921600 baud**, then click **Connect**. Close
Arduino Serial Monitor and other applications using the port first.

Launchers prefer `dist/ADXL345_Monitor.exe` if it has been built locally; otherwise
they use `.venv/Scripts/pythonw.exe`. They work when invoked from another folder.

## XYZ Graphs

X is blue, Y green, and Z orange. Each axis has a live value and its own trace.
Values are acceleration in sensor coordinates, including gravity.

- **History:** show the latest 2, 5, 10, 30, or 60 seconds on a nominal time scale.
- **Units:** display g or m/s²; `1 g = 9.80665 m/s²`.
- **Auto-scale Y:** fit axes independently. Disable it for the fixed +/-16 g range.
- **Pause graphs:** freeze displayed curves and values while reception and active
  CSV recording continue. Resume returns to the newest history.
- **Record CSV / Stop CSV:** save original received samples from the moment the
  file is opened. Earlier on-screen history is not exported.

Graphs target 25 frames/s. Downsampling retains short minima/maxima rather than
simply skipping points. Changing units, history, or scaling does not change CSV
values. A stationary sensor normally has a total magnitude near 1 g.

## 3D Orientation

The same serial stream controls a software-rendered board model, with no OpenGL
dependency. Slowly tilt the board about X and Y.

- **Roll X / Pitch Y:** two tilt estimates derived from the gravity vector.
- **Z from vertical:** the angle between sensor Z and vertical, 0–180°; it is not
  a third independent rotation angle.
- **Set reference:** store the gravity direction and show a gray dashed reference
  model. The button requires fresh, gravity-like data.
- **From reference:** angle between current/reference gravity directions in sensor
  coordinates. It is not the complete spatial rotation angle.
- **Clear reference:** remove that comparison.
- **Smoothing:** choose 0.08, 0.25, 0.50, or 1.00 s. Larger values reduce jitter
  with more response delay; raw plots and CSV are unchanged.
- **Pause model:** freeze this view independently of graph pause and recording.

The model targets 50 frames/s. The vector is filtered before converting to
angles, avoiding an incorrect average through the +/-180° wrap. Continuous
quaternion pose updates avoid artificial Euler-branch flips near vertical X.
At vertical X, roll is undefined and displayed as “—”.

Green quality text means the estimate looks gravity-like, not that its accuracy
has been proven. Orange messages identify stale data, undefined direction, or
acceleration that can distort tilt. Suspect angles use `≈`. Strong acceleration
or free fall holds the last pose. A magnitude near 1 g alone does not rule out
linear acceleration. Smoothing does not replace calibration.

**Limits:** ADXL345 alone cannot measure heading/yaw about world vertical,
reconstruct a stable XYZ travel path, or provide full six-degree-of-freedom
tracking. This is a gravity-based tilt demonstration. See
[Analog Devices AN-1057](https://www.analog.com/en/resources/app-notes/an-1057.html)
for the method and limitations.

## Recording and time

CSV columns are `sample,t_est_s,pc_rx_time_utc,x_g,y_g,z_g,gap_before`.
Values remain in g regardless of display units. Switching tabs or pausing a view
does not interrupt active recording; disconnecting or closing the app finishes it.
CSV writing happens before the interface queue, so UI-only drops do not remove
those already received samples from an active recording.

`sample` is the PC count since connection and can be nonzero when recording starts.
`t_est_s = sample / 800` is nominal time. `pc_rx_time_utc` is PC batch processing
time; several rows can share it. Neither is an individual sensor timestamp.
Known warnings, malformed lines, and restarts mark `gap_before=1`; exact loss
position and duration are unknown. Unreported individual line loss cannot be
detected by this protocol. See [serial-protocol.md](../../docs/serial-protocol.md).

## Stream health

The footer shows valid sample count, recent PC reception rate, bad lines,
warnings, and UI-only dropped samples. USB batching causes short-term rate
variation. The tested unit ran near 785.7 samples/s with nominal 800 Hz configured.

When recording is inactive, the footer also shows INT1 edges, FIFO full events,
firmware queue drops, and interrupt timeouts. These are cumulative firmware
counters, not current FIFO occupancy. They can predate the PC connection. During
recording the footer shows CSV progress; warning messages still enter the log.

## Tests and standalone EXE

```powershell
.\scripts\Run_Tests.cmd
.\scripts\Build_EXE.cmd
```

The optional EXE build installs the pinned PyInstaller version from
`requirements-build.txt`. Output is `dist/ADXL345_Monitor.exe`; intermediate files
go to `build/`. Neither is committed. A built EXE can be copied to a Windows PC
without Python. Setup, build, and test helpers accept `/nopause` for automation.

## Python CLI

From this folder, with the appropriate Python environment active:

```powershell
python -m pip install -r requirements.txt
python -m pc_monitor.app
python -m pc_monitor.app --demo --orientation
python -m pc_monitor.app --port COM16 --baud 921600
python -m unittest discover -s tests -v
```

Python source can also run on systems with Tkinter and pySerial; the supplied
`.cmd` helpers and packaged EXE build are for Windows.

## Optional real-board check

Disconnect the GUI from the board first, then run:

```powershell
.\.venv\Scripts\python.exe verify_board.py --port COM16 --seconds 60 --require-irq
```

The utility saves CSV/JSON under the ignored `captures/` directory. `--output`
selects another basename. `--reset` intentionally resets ESP32 using RTS; use it
only when wanted. No reset or upload is performed by the normal source tests.

## Troubleshooting

- **No COM port:** check the USB data cable, USB-UART driver, and selected connector.
- **Access denied:** close other serial programs using the port.
- **Connected, no data:** confirm 921600 baud, SPI/power wiring, and INT1 → GPIO4;
  inspect the startup/wiring-test messages and timeout count.
- **Large jumps in tilt:** use gentle movement and review quality messages;
  linear acceleration can resemble tilt.
- **CSV write error:** inspect the log and choose a writable path with free space.
- **Demo is active:** click Stop demo before connecting real hardware.
