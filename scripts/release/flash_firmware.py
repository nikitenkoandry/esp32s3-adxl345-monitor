"""Verify release images, then explicitly flash one Windows COM port.

--check uses only the standard library and never opens hardware. Normal upload
uses esptool in this interpreter, with the four-image ESP-IDF flash layout.
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys


IMAGES = {
    "0x0": "bootloader/bootloader.bin",
    "0x8000": "partition_table/partition-table.bin",
    "0xe000": "ota_data_initial.bin",
    "0x10000": "adxl345_monitor.bin",
}


def verify_images(folder):
    manifest = json.loads((folder / "firmware-manifest.json").read_text(encoding="utf-8"))
    images = manifest["images"]
    if len(images) != len(IMAGES) or {
        item["address"]: item["file"] for item in images
    } != IMAGES:
        raise ValueError("Expected the four ESP32-S3 release images")
    for item in images:
        data = (folder / item["file"]).read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Image checksum mismatch: " + item["file"])
    print("All four firmware image sizes and SHA-256 checksums match.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", help="Explicit USB-UART port, e.g. COM16")
    parser.add_argument("--check", action="store_true", help="Check without accessing hardware")
    args = parser.parse_args()
    if args.port and not re.fullmatch(r"COM[1-9][0-9]*", args.port, re.IGNORECASE):
        parser.error("Port must be a Windows COM name such as COM16")
    if not args.check and not args.port:
        parser.error("An explicit COM port is required for flashing")
    folder = Path(__file__).resolve().parent
    verify_images(folder)
    if args.check:
        return 0
    if importlib.metadata.version("esptool") != "5.3.1":
        raise ValueError("Use esptool 5.3.1 from requirements-flash.txt")
    command = [
        sys.executable, "-m", "esptool", "--chip", "esp32s3",
        "--port", args.port.upper(), "--baud", "460800",
        "--before", "default-reset", "--after", "hard-reset", "write-flash",
        "--flash-mode", "dio", "--flash-freq", "80m", "--flash-size", "16MB",
    ]
    for address, filename in IMAGES.items():
        command.extend([address, filename])
    print("Replacing installed firmware on " + args.port.upper(), flush=True)
    return subprocess.run(command, cwd=folder, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, importlib.metadata.PackageNotFoundError) as error:
        print("Flash failed: " + str(error), file=sys.stderr)
        raise SystemExit(1)
