"""Package the verified v1.0.0 firmware and Windows EXE; never flash/publish."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VERSION = "v1.0.0"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def encode_json(value):
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def write_zip(path, files):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            # Stable paths, ordering and timestamps for identical inputs.
            entry = zipfile.ZipInfo(name, (2026, 11, 20, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, data)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError("Archive verification failed: " + path.name)


def main():
    manifest = json.loads((HERE / "verified-firmware-v1.0.0.json").read_text(encoding="utf-8"))
    # Matching binaries must not hide later firmware/application source edits.
    source_paths = ["firmware/main", "firmware/CMakeLists.txt",
                    "firmware/sdkconfig.defaults", "firmware/partitions.csv",
                    "tools/monitor/pc_monitor", "tools/monitor/ADXL345_Monitor.pyw",
                    "tools/monitor/requirements.txt", "tools/monitor/requirements-build.txt"]
    if git("diff", manifest["firmware_source_commit"], "--", *source_paths):
        raise ValueError("Application sources differ from the verified revision")
    firmware = {}
    for item in manifest["images"]:
        data = (ROOT / "firmware/build" / item["file"]).read_bytes()
        if len(data) != item["bytes"] or sha256(data) != item["sha256"]:
            raise ValueError("Not the hardware-verified image: " + item["file"])
        firmware[item["file"]] = data

    exe = (ROOT / "tools/monitor/dist/ADXL345_Monitor.exe").read_bytes()
    pe_offset = struct.unpack_from("<I", exe, 0x3C)[0]
    if (exe[:2] != b"MZ" or exe[pe_offset:pe_offset + 4] != b"PE\0\0"
            or struct.unpack_from("<H", exe, pe_offset + 4)[0] != 0x8664):
        raise ValueError("Expected a Windows x64 monitor EXE")

    guide = (ROOT / "docs/quick-start.md").read_text(encoding="utf-8")
    common = {"QUICK_START.md": guide.replace(
        "](images/", "](screenshots/").encode("utf-8")}
    for filename in ("ui-xyz-graphs.png", "ui-3d-orientation.png"):
        common["screenshots/" + filename] = (ROOT / "docs/images" / filename).read_bytes()
    firmware.update(common)
    firmware["firmware-manifest.json"] = encode_json(manifest)
    for name in ("Flash_Firmware.cmd", "flash_firmware.py", "requirements-flash.txt"):
        data = (HERE / name).read_bytes()
        if name.endswith(".cmd"):
            data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        firmware[name] = data

    monitor = dict(common)
    monitor["ADXL345_Monitor.exe"] = exe
    monitor["Start_Demo.cmd"] = b'@echo off\r\nstart "" "%~dp0ADXL345_Monitor.exe" --demo --orientation\r\n'
    monitor["monitor-manifest.json"] = encode_json({
        "release_version": VERSION, "source_commit": git("rev-parse", "HEAD"),
        "platform": "Windows x64", "python": sys.version.split()[0],
        "pyinstaller": importlib.metadata.version("pyinstaller"),
        "file": "ADXL345_Monitor.exe", "bytes": len(exe), "sha256": sha256(exe),
    })
    for files in (firmware, monitor):
        files["SHA256SUMS.txt"] = "".join(
            sha256(data) + "  " + name + "\n" for name, data in sorted(files.items())
        ).encode("ascii")

    output = ROOT / "dist" / VERSION
    output.mkdir(parents=True, exist_ok=True)
    write_zip(output / f"esp32s3-adxl345-firmware-{VERSION}.zip", firmware)
    write_zip(output / f"ADXL345-Monitor-Windows-x64-{VERSION}.zip", monitor)
    image_url = f"https://raw.githubusercontent.com/nikitenkoandry/esp32s3-adxl345-monitor/{VERSION}/docs/images/"
    (output / "QUICK_START.md").write_text(guide.replace(
        "](images/", "](" + image_url), encoding="utf-8", newline="\n")
    assets = [output / f"esp32s3-adxl345-firmware-{VERSION}.zip",
              output / f"ADXL345-Monitor-Windows-x64-{VERSION}.zip", output / "QUICK_START.md"]
    (output / "SHA256SUMS.txt").write_text("".join(
        sha256(path.read_bytes()) + "  " + path.name + "\n" for path in assets
    ), encoding="ascii", newline="\n")
    for path in [*assets, output / "SHA256SUMS.txt"]:
        print(f"{path.name}: {path.stat().st_size:,} bytes")
    print("Verified image hashes, source revision, x64 EXE, and ZIP contents.")


if __name__ == "__main__":
    main()
