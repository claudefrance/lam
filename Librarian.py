#!/usr/bin/env python3
"""
D-50 VST Bank Librarian
=======================
Dual-bank patch editor for Roland D-50 / D-50 Cloud VST .bin files.

Features:
  - Load two banks side-by-side
  - Display all 64 patch names (with Extended-Wave warning)
  - Copy or Move selected patches from one bank to the other
  - Choose exact destination slot (11-88)
  - Swap two patches
  - Clear / Initialize a slot
  - Save either bank as a new .bin (KoaBankFile format)
  - Optional export of a bank to hardware SysEx (.syx)

Requires: Python 3.8+ (Tkinter included in standard library)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
from pathlib import Path
from copy import deepcopy

# ---------------------------------------------------------------------------
# Format constants (reverse-engineered from KoaBankFile)
# ---------------------------------------------------------------------------
BIN_MAGIC = b"KoaBankFile00003PG-D50"
HEADER_SIZE = 22
BLOCK_SIZE = 468
NAME_LEN = 18
PATCH_DATA_LEN = 448
NUM_PATCHES = 64
MAX_HARDWARE_PCM = 100

PCM_WAVE_CANDIDATE_OFFSETS = [
    0x07, 0x3F, 0x77, 0xAF,
    0x08, 0x40, 0x78, 0xB0,
    0x1F, 0x57, 0x8F, 0xC7,
]

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def detect_extended_waves(patch_data: bytes) -> bool:
    for off in PCM_WAVE_CANDIDATE_OFFSETS:
        if off < len(patch_data) and patch_data[off] > MAX_HARDWARE_PCM:
            return True
    for off in range(min(len(patch_data), 300)):
        val = patch_data[off]
        if 101 <= val <= 127:
            prev = patch_data[off - 1] if off > 0 else 0
            nxt = patch_data[off + 1] if off + 1 < len(patch_data) else 0
            if prev < 30 and nxt < 40:
                return True
    return False


def empty_patch(name: str = "Init Patch") -> tuple:
    """Return (name, 448-byte data, uses_ext=False)"""
    name_bytes = name.encode("ascii", errors="replace")[:NAME_LEN].ljust(NAME_LEN, b" ")
    # Minimal silent init (all zeros is acceptable for the data part)
    data = bytes(PATCH_DATA_LEN)
    return (name.rstrip(), data, False)


def parse_bin(data: bytes) -> list:
    """
    Parse a KoaBankFile .bin → list of 64 tuples (name, data448, uses_ext)
    """
    if not data[:15].startswith(b"KoaBankFile"):
        raise ValueError("Not a recognised D-50 VST KoaBankFile (.bin)")

    patches = []
    offset = HEADER_SIZE
    for i in range(NUM_PATCHES):
        if offset + BLOCK_SIZE > len(data):
            patches.append(empty_patch(f"(empty {i+1})"))
            continue
        block = data[offset:offset + BLOCK_SIZE]
        name = block[:NAME_LEN].decode("ascii", errors="replace").rstrip(" \x00")
        param = block[20:20 + PATCH_DATA_LEN]
        if len(param) < PATCH_DATA_LEN:
            param = param.ljust(PATCH_DATA_LEN, b"\x00")
        uses_ext = detect_extended_waves(param)
        patches.append((name, param, uses_ext))
        offset += BLOCK_SIZE

    while len(patches) < NUM_PATCHES:
        patches.append(empty_patch(f"(empty {len(patches)+1})"))
    return patches


def build_bin(patches: list) -> bytes:
    """Rebuild a complete KoaBankFile .bin from 64 patch tuples."""
    out = bytearray(BIN_MAGIC)
    for name, data, _ in patches:
        name_bytes = name.encode("ascii", errors="replace")[:NAME_LEN].ljust(NAME_LEN, b" ")
        # Layout: 18 name + 2 zero padding + 448 data = 468
        block = name_bytes + b"\x00\x00" + data[:PATCH_DATA_LEN].ljust(PATCH_DATA_LEN, b"\x00")
        out.extend(block)
    return bytes(out)


def roland_checksum(data: bytes) -> int:
    s = sum(data) & 0x7F
    return (128 - s) & 0x7F


def build_dt1(address: tuple, data: bytes, device_id: int = 0x00) -> bytes:
    body = bytes(address) + data
    cs = roland_checksum(body)
    return bytes([0xF0, 0x41, device_id, 0x14, 0x12]) + body + bytes([cs, 0xF7])


def build_sysex(patches: list) -> bytes:
    all_data = b"".join(p[1] for p in patches)
    TOTAL = 34688
    payload = all_data + bytes(TOTAL - len(all_data))
    messages = []
    addr = 0x020000
    pos = 0
    while pos < len(payload):
        chunk_size = 256 if (len(payload) - pos) >= 256 else len(payload) - pos
        if pos + chunk_size >= TOTAL and chunk_size > 128:
            chunk_size = 128
        chunk = payload[pos:pos + chunk_size]
        a1 = (addr >> 16) & 0x7F
        a2 = (addr >> 8) & 0x7F
        a3 = addr & 0x7F
        messages.append(build_dt1((a1, a2, a3), chunk))
        addr += chunk_size
        pos += chunk_size
    return b"".join(messages)


def slot_label(index: int) -> str:
    """0-based index → '11'..'88'"""
    bank = index // 8 + 1
    num = index % 8 + 1
    return f"{bank}{num}"


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class BankPanel(ttk.LabelFrame):
    """One side of the dual librarian (Bank A or Bank B)."""

    def __init__(self, parent, title: str, app):
        super().__init__(parent, text=title, padding=4)
        self.app = app
        self.patches = [empty_patch(f"Init {i+1}") for i in range(NUM_PATCHES)]
        self.filepath = None
        self.dirty = False

        # Toolbar
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(bar, text="Load .bin…", command=self.load).pack(side=tk.LEFT, padx=1)
        ttk.Button(bar, text="Save .bin…", command=self.save).pack(side=tk.LEFT, padx=1)
        ttk.Button(bar, text="Export .syx…", command=self.export_syx).pack(side=tk.LEFT, padx=1)
        ttk.Button(bar, text="Clear All", command=self.clear_all).pack(side=tk.LEFT, padx=1)

        self.status = ttk.Label(bar, text="Empty bank", foreground="#666")
        self.status.pack(side=tk.RIGHT, padx=4)

        # Treeview
        cols = ("slot", "name", "flag")
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 selectmode="extended", height=22)
        self.tree.heading("slot", text="#")
        self.tree.heading("name", text="Patch Name")
        self.tree.heading("flag", text="")
        self.tree.column("slot", width=36, anchor="center")
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("flag", width=28, anchor="center")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("ok", background="#e8f5e9")
        self.tree.tag_configure("ext", background="#fff3e0")
        self.tree.tag_configure("empty", background="#f0f0f0")

        self.tree.bind("<<TreeviewSelect>>", lambda e: self.app.on_selection_changed())
        self.tree.bind("<Double-1>", self._on_double_click)

        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        ext_count = 0
        for i, (name, data, uses_ext) in enumerate(self.patches):
            flag = "⚠" if uses_ext else ""
            tag = "ext" if uses_ext else ("empty" if not name or name.startswith("Init") else "ok")
            if uses_ext:
                ext_count += 1
            self.tree.insert("", "end", iid=str(i),
                             values=(slot_label(i), name, flag), tags=(tag,))
        name = os.path.basename(self.filepath) if self.filepath else "(untitled)"
        dirty = " *" if self.dirty else ""
        self.status.config(text=f"{name}{dirty}  |  {ext_count} ext.")

    def selected_indices(self) -> list:
        return [int(iid) for iid in self.tree.selection()]

    def load(self):
        path = filedialog.askopenfilename(
            title="Load D-50 VST bank",
            filetypes=[("D-50 VST Bank", "*.bin"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.patches = parse_bin(data)
            self.filepath = path
            self.dirty = False
            self.refresh()
            self.app.log(f"Loaded {os.path.basename(path)} into {self.cget('text')}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save(self):
        default = os.path.basename(self.filepath) if self.filepath else "new_bank.bin"
        path = filedialog.asksaveasfilename(
            title="Save bank as .bin",
            defaultextension=".bin",
            initialfile=default,
            filetypes=[("D-50 VST Bank", "*.bin"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            data = build_bin(self.patches)
            with open(path, "wb") as f:
                f.write(data)
            self.filepath = path
            self.dirty = False
            self.refresh()
            self.app.log(f"Saved {os.path.basename(path)}")
            messagebox.showinfo("Saved", f"Bank saved:\n{path}\n({len(data)} bytes)")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_syx(self):
        default = (Path(self.filepath).stem + ".syx") if self.filepath else "bank.syx"
        path = filedialog.asksaveasfilename(
            title="Export as SysEx",
            defaultextension=".syx",
            initialfile=default,
            filetypes=[("SysEx", "*.syx"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            syx = build_sysex(self.patches)
            with open(path, "wb") as f:
                f.write(syx)
            self.app.log(f"Exported SysEx → {os.path.basename(path)}")
            messagebox.showinfo("Exported", f"SysEx saved ({len(syx)} bytes):\n{path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def clear_all(self):
        if not messagebox.askyesno("Confirm", "Clear all 64 patches in this bank?"):
            return
        self.patches = [empty_patch(f"Init {i+1}") for i in range(NUM_PATCHES)]
        self.dirty = True
        self.refresh()
        self.app.log(f"Cleared {self.cget('text')}")

    def _on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        idx = int(item)
        old_name = self.patches[idx][0]
        new_name = simpledialog.askstring("Rename patch", "New name (max 18 chars):",
                                          initialvalue=old_name)
        if new_name is not None:
            new_name = new_name[:18]
            data = self.patches[idx][1]
            uses_ext = self.patches[idx][2]
            self.patches[idx] = (new_name, data, uses_ext)
            self.dirty = True
            self.refresh()


class D50LibrarianApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("D-50 VST Bank Librarian – Build banks from multiple sources")
        self.geometry("980x700")
        self.minsize(800, 560)

        # Main horizontal split
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.bank_a = BankPanel(paned, "Bank A (Source / Destination)", self)
        self.bank_b = BankPanel(paned, "Bank B (Source / Destination)", self)
        paned.add(self.bank_a, weight=1)
        paned.add(self.bank_b, weight=1)

        # Center action buttons
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(action_frame, text="Actions:").pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(action_frame, text="Copy A → B", command=lambda: self.copy_move("A", "B", move=False)).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Move A → B", command=lambda: self.copy_move("A", "B", move=True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Copy B → A", command=lambda: self.copy_move("B", "A", move=False)).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Move B → A", command=lambda: self.copy_move("B", "A", move=True)).pack(side=tk.LEFT, padx=2)

        ttk.Separator(action_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(action_frame, text="Swap selected", command=self.swap_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Copy to chosen slot…", command=self.copy_to_slot).pack(side=tk.LEFT, padx=2)

        # Log / help
        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.pack(fill=tk.X, padx=6, pady=(0, 6))
        self.log_text = tk.Text(log_frame, height=4, wrap=tk.WORD, state="disabled",
                                font=("Consolas", 9))
        self.log_text.pack(fill=tk.X)
        self.log("Ready. Load banks on left and/or right, select patches, then use the action buttons.")
        self.log("Tip: Double-click a patch name to rename it. Extended waves (⚠) only exist in the VST.")

    def log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def on_selection_changed(self):
        pass  # reserved for future status updates

    def _get_banks(self, src_side: str, dst_side: str):
        src = self.bank_a if src_side == "A" else self.bank_b
        dst = self.bank_a if dst_side == "A" else self.bank_b
        return src, dst

    def copy_move(self, src_side: str, dst_side: str, move: bool = False):
        src, dst = self._get_banks(src_side, dst_side)
        indices = src.selected_indices()
        if not indices:
            messagebox.showwarning("No selection", f"Select one or more patches in Bank {src_side} first.")
            return

        # Ask for starting destination slot
        first_slot = simpledialog.askstring(
            "Destination slot",
            f"Paste {len(indices)} patch(es) starting at which slot?\n"
            f"(Enter 11-88, or leave empty to fill first empty slots)",
            initialvalue=slot_label(indices[0])
        )
        if first_slot is None:
            return

        if first_slot.strip() == "":
            # find first empty-ish slots
            dest_indices = []
            for i, (name, _, _) in enumerate(dst.patches):
                if name.startswith("Init") or name.startswith("(empty"):
                    dest_indices.append(i)
                    if len(dest_indices) == len(indices):
                        break
            if len(dest_indices) < len(indices):
                messagebox.showwarning("Not enough empty slots",
                                       "Not enough empty slots found. Specify a starting slot.")
                return
        else:
            try:
                # parse "11" → 0, "88" → 63
                s = first_slot.strip()
                bank = int(s[0])
                num = int(s[1])
                start = (bank - 1) * 8 + (num - 1)
                if not (0 <= start < 64):
                    raise ValueError
                dest_indices = list(range(start, min(start + len(indices), 64)))
                if len(dest_indices) < len(indices):
                    messagebox.showwarning("Overflow", "Not enough room from that starting slot.")
                    return
            except Exception:
                messagebox.showerror("Invalid slot", "Please enter a slot like 11, 23, 88 …")
                return

        # Perform copy / move
        for src_idx, dst_idx in zip(indices, dest_indices):
            name, data, ext = src.patches[src_idx]
            dst.patches[dst_idx] = (name, data, ext)
            if move:
                src.patches[src_idx] = empty_patch(f"Init {src_idx+1}")

        src.dirty = move
        dst.dirty = True
        src.refresh()
        dst.refresh()
        action = "Moved" if move else "Copied"
        self.log(f"{action} {len(indices)} patch(es) from Bank {src_side} → Bank {dst_side}")

    def copy_to_slot(self):
        """Copy the first selected patch of the focused bank to a user-chosen slot in the other bank."""
        # Determine which bank has selection
        sel_a = self.bank_a.selected_indices()
        sel_b = self.bank_b.selected_indices()
        if sel_a and not sel_b:
            src, dst, src_side, dst_side = self.bank_a, self.bank_b, "A", "B"
            src_idx = sel_a[0]
        elif sel_b and not sel_a:
            src, dst, src_side, dst_side = self.bank_b, self.bank_a, "B", "A"
            src_idx = sel_b[0]
        elif sel_a and sel_b:
            messagebox.showinfo("Ambiguous", "Select patches in only one bank, then choose destination slot.")
            return
        else:
            messagebox.showwarning("No selection", "Select a patch in one of the banks first.")
            return

        slot = simpledialog.askstring("Destination slot",
                                      f"Copy «{src.patches[src_idx][0]}» to which slot in Bank {dst_side}?\n(11-88)",
                                      initialvalue="11")
        if not slot:
            return
        try:
            bank = int(slot.strip()[0])
            num = int(slot.strip()[1])
            dst_idx = (bank - 1) * 8 + (num - 1)
            if not (0 <= dst_idx < 64):
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid", "Enter a valid slot (11-88).")
            return

        name, data, ext = src.patches[src_idx]
        dst.patches[dst_idx] = (name, data, ext)
        dst.dirty = True
        dst.refresh()
        self.log(f"Copied «{name}» → Bank {dst_side} slot {slot_label(dst_idx)}")

    def swap_selected(self):
        sel_a = self.bank_a.selected_indices()
        sel_b = self.bank_b.selected_indices()
        if len(sel_a) != 1 or len(sel_b) != 1:
            messagebox.showwarning("Selection", "Select exactly one patch in Bank A and one in Bank B.")
            return
        ia, ib = sel_a[0], sel_b[0]
        self.bank_a.patches[ia], self.bank_b.patches[ib] = \
            self.bank_b.patches[ib], self.bank_a.patches[ia]
        self.bank_a.dirty = True
        self.bank_b.dirty = True
        self.bank_a.refresh()
        self.bank_b.refresh()
        self.log(f"Swapped Bank A {slot_label(ia)} ↔ Bank B {slot_label(ib)}")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = D50LibrarianApp()
    app.mainloop()
