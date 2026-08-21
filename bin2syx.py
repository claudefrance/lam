#!/usr/bin/env python3
"""
Roland D-50 VST (.bin) → Hardware SysEx (.syx) Converter
=======================================================
GUI tool that:
  - Loads KoaBankFile .bin banks exported by the Roland D-50 / D-50 Cloud VST
  - Displays all 64 patch names
  - Highlights in orange/yellow patches that use Extended PCM waves
    (wave numbers > 100) which the original hardware D-50/D-550/D-05
    cannot play correctly
  - Converts the bank to a standard 36048-byte Roland DT1 SysEx dump
    ready to send to hardware

Requires: Python 3.8+ (Tkinter is part of the standard library)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import struct
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BIN_MAGIC = b"KoaBankFile00003PG-D50"
HEADER_SIZE = 22
BLOCK_SIZE = 468          # 18-byte name + 2 padding + 448 parameter bytes
NAME_LEN = 18
PATCH_DATA_LEN = 448      # classic D-50 patch size (incl. name in memory map)
NUM_PATCHES = 64

# Roland SysEx
ROLAND_ID = 0x41
MODEL_ID = 0x14           # D-50
CMD_DT1 = 0x12
DEVICE_ID = 0x00          # channel 1 (device ID = channel-1)

# Hardware PCM waves are 1..100. Plugin can go higher (extended waves).
MAX_HARDWARE_PCM = 100

# Approximate offsets of the four PCM Wave Number parameters inside the
# 448-byte patch data (after the 18-byte name that is stored in the BIN).
# These are derived from the official MIDI implementation + observed data.
# Each Tone has two Partials; each Partial has a WG PCM Wave No. at a
# fixed relative location when the structure uses PCM.
# We scan a few candidate offsets that commonly hold the wave select.
PCM_WAVE_CANDIDATE_OFFSETS = [
    # Upper Tone Partial 1 & 2, Lower Tone Partial 1 & 2 (empirical)
    0x07, 0x3F, 0x77, 0xAF,   # classic partial parameter layout
    0x08, 0x40, 0x78, 0xB0,
    0x1F, 0x57, 0x8F, 0xC7,
]


def roland_checksum(data: bytes) -> int:
    """Roland checksum = 128 - (sum of address+data) % 128"""
    s = sum(data) & 0x7F
    return (128 - s) & 0x7F


def build_dt1(address: tuple, data: bytes, device_id: int = DEVICE_ID) -> bytes:
    """Build a single Roland DT1 SysEx message."""
    addr_bytes = bytes(address)
    body = addr_bytes + data
    cs = roland_checksum(body)
    return bytes([0xF0, ROLAND_ID, device_id, MODEL_ID, CMD_DT1]) + body + bytes([cs, 0xF7])


def extract_patches_from_bin(data: bytes):
    """
    Parse a KoaBankFile .bin and return list of (name, patch_bytes_448, uses_ext).
    """
    if not data.startswith(BIN_MAGIC):
        # tolerate small variations of the magic
        if not data[:15].startswith(b"KoaBankFile"):
            raise ValueError("Not a recognised D-50 VST KoaBankFile (.bin)")

    patches = []
    offset = HEADER_SIZE
    for i in range(NUM_PATCHES):
        if offset + BLOCK_SIZE > len(data):
            break
        block = data[offset:offset + BLOCK_SIZE]
        name_raw = block[:NAME_LEN]
        name = name_raw.decode("ascii", errors="replace").rstrip(" \x00")
        # parameter data that will become the 448-byte patch in memory
        # BIN layout: 18 name + 2 zero padding + 448 data  OR  18 name + 450 data
        # We take the 448 bytes that match the hardware memory image.
        param = block[20:20 + PATCH_DATA_LEN]
        if len(param) < PATCH_DATA_LEN:
            param = param.ljust(PATCH_DATA_LEN, b"\x00")

        uses_ext = detect_extended_waves(param)
        patches.append((name, param, uses_ext))
        offset += BLOCK_SIZE

    # pad to 64 if the file was truncated
    while len(patches) < NUM_PATCHES:
        patches.append((f"(empty {len(patches)+1})", bytes(PATCH_DATA_LEN), False))

    return patches


def detect_extended_waves(patch_data: bytes) -> bool:
    """
    Heuristic: look at candidate offsets for PCM wave numbers.
    If any value is > MAX_HARDWARE_PCM (and looks like a wave select,
    i.e. not a random high parameter), flag the patch.
    """
    for off in PCM_WAVE_CANDIDATE_OFFSETS:
        if off < len(patch_data):
            val = patch_data[off]
            if val > MAX_HARDWARE_PCM:
                return True
    # extra safety: scan the whole partial areas for any byte in 101-127
    # that sits in a typical wave-select position pattern
    for off in range(0, min(len(patch_data), 300), 1):
        val = patch_data[off]
        if 101 <= val <= 127:
            # crude context check – neighbouring bytes often low
            prev = patch_data[off - 1] if off > 0 else 0
            nxt = patch_data[off + 1] if off + 1 < len(patch_data) else 0
            if prev < 30 and nxt < 40:
                return True
    return False


def build_sysex_bank(patches) -> bytes:
    """
    Build a complete 36048-byte D-50 bank SysEx dump from the list of
    448-byte patch parameter blocks.
    Memory layout used by the hardware:
      Address 02 00 00 … – patch data (64 × 448 bytes = 28672)
      then reverb / remaining memory to fill the classic dump size.
    """
    # Concatenate all 64 patches (exactly 64*448 = 28672 bytes)
    all_patch_data = b"".join(p[1] for p in patches)
    assert len(all_patch_data) == 64 * PATCH_DATA_LEN

    # Classic full dumps also contain the 16 reverb types and a few
    # extra memory areas.  For maximum compatibility we emit the same
    # number of DT1 messages as a real hardware dump (136 messages).
    # We place the patch data starting at address 02 00 00 and fill the
    # rest with zeros (safe default reverb).

    # Total data payload that produces a 36048-byte file:
    # 135 messages of 256 data bytes + 1 message of 128 data bytes
    # = 135*256 + 128 = 34688 bytes of pure data
    TOTAL_DATA = 34688
    payload = all_patch_data + bytes(TOTAL_DATA - len(all_patch_data))

    messages = []
    addr = 0x020000          # start of temporary / patch memory area
    pos = 0
    while pos < len(payload):
        chunk_size = 256 if (len(payload) - pos) >= 256 else (len(payload) - pos)
        # last chunk of a classic dump is 128 bytes
        if pos + chunk_size >= TOTAL_DATA and chunk_size > 128:
            chunk_size = 128
        chunk = payload[pos:pos + chunk_size]

        a1 = (addr >> 16) & 0x7F
        a2 = (addr >> 8) & 0x7F
        a3 = addr & 0x7F
        messages.append(build_dt1((a1, a2, a3), chunk))

        # Roland address advances by the number of bytes written
        # (each address step is one byte in the 7-bit mapped space)
        addr += chunk_size
        pos += chunk_size

    return b"".join(messages)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class D50ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("D-50 VST .bin → Hardware SysEx Converter")
        self.geometry("780x620")
        self.minsize(640, 480)

        self.patches = []          # list of (name, data, uses_ext)
        self.bin_path = None

        self._build_ui()

    def _build_ui(self):
        # Top toolbar
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(toolbar, text="Open .bin…", command=self.open_bin).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Convert & Save .syx…", command=self.save_syx).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear", command=self.clear).pack(side=tk.LEFT, padx=2)

        self.status = ttk.Label(toolbar, text="No file loaded", foreground="#555")
        self.status.pack(side=tk.RIGHT, padx=8)

        # Legend
        legend = ttk.Frame(self, padding=(8, 2))
        legend.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(legend, text="Legend:").pack(side=tk.LEFT)
        ttk.Label(legend, text="  Normal patch", background="#e8f5e9",
                  relief="solid", padding=(6, 1)).pack(side=tk.LEFT, padx=4)
        ttk.Label(legend, text="  Uses Extended Waves (VST only)",
                  background="#fff3e0", relief="solid", padding=(6, 1)).pack(side=tk.LEFT, padx=4)

        # Patch list with scrollbar
        list_frame = ttk.Frame(self, padding=6)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = ("idx", "name", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                 selectmode="browse")
        self.tree.heading("idx", text="#")
        self.tree.heading("name", text="Patch Name")
        self.tree.heading("status", text="Compatibility")
        self.tree.column("idx", width=40, anchor="center")
        self.tree.column("name", width=280, anchor="w")
        self.tree.column("status", width=220, anchor="w")

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Colour tags
        self.tree.tag_configure("ok", background="#e8f5e9")
        self.tree.tag_configure("ext", background="#fff3e0")
        self.tree.tag_configure("empty", background="#f5f5f5")

        # Bottom info
        info = ttk.Label(self, text=(
            "Extended waves (PCM > 100) exist only in the Roland Cloud / VST plugin. "
            "They will be silent or substituted on real D-50 / D-550 / D-05 hardware."
        ), wraplength=740, foreground="#444", padding=8)
        info.pack(side=tk.BOTTOM, fill=tk.X)

    def open_bin(self):
        path = filedialog.askopenfilename(
            title="Select D-50 VST bank (.bin)",
            filetypes=[("D-50 VST Bank", "*.bin"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.patches = extract_patches_from_bin(data)
            self.bin_path = path
            self._refresh_list()
            ext_count = sum(1 for p in self.patches if p[2])
            self.status.config(
                text=f"Loaded: {os.path.basename(path)}  —  "
                     f"{len(self.patches)} patches, {ext_count} use extended waves"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{e}")

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for i, (name, _, uses_ext) in enumerate(self.patches):
            bank = i // 8 + 1
            num = i % 8 + 1
            idx = f"{bank}{num}"
            if not name or name.startswith("(empty"):
                status = "Empty"
                tag = "empty"
            elif uses_ext:
                status = "⚠ Extended Waves (VST only)"
                tag = "ext"
            else:
                status = "✓ Hardware compatible"
                tag = "ok"
            self.tree.insert("", "end", values=(idx, name, status), tags=(tag,))

    def save_syx(self):
        if not self.patches:
            messagebox.showwarning("No data", "Please open a .bin file first.")
            return
        default_name = "converted.syx"
        if self.bin_path:
            default_name = Path(self.bin_path).stem + ".syx"
        path = filedialog.asksaveasfilename(
            title="Save SysEx bank",
            defaultextension=".syx",
            initialfile=default_name,
            filetypes=[("SysEx files", "*.syx"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            syx = build_sysex_bank(self.patches)
            with open(path, "wb") as f:
                f.write(syx)
            messagebox.showinfo(
                "Success",
                f"SysEx bank saved:\n{path}\n\n"
                f"Size: {len(syx)} bytes\n"
                f"You can now send it to your D-50 / D-550 / D-05 with any SysEx utility."
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write SysEx:\n{e}")

    def clear(self):
        self.patches = []
        self.bin_path = None
        self.tree.delete(*self.tree.get_children())
        self.status.config(text="No file loaded")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = D50ConverterApp()
    app.mainloop()
