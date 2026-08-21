#!/usr/bin/env python3
"""
Roland D-50 / D-550 Bank Reader
- Supports classic SysEx (.syx) bulk dumps
- Supports D-50 VSTi / Roland Cloud .bin banks (KoaBankFile format)
- Displays the 64 patch names
- Can export the list to a TXT file
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os

# ---------------------------------------------------------------------------
# Roland D-50 SysEx helpers
# ---------------------------------------------------------------------------

ROLAND_ID = 0x41
MODEL_ID  = 0x14          # D-50 / D-550
CMD_DT1   = 0x12

CHARSET = (
    [' '] +
    [chr(c) for c in range(ord('A'), ord('Z') + 1)] +
    [chr(c) for c in range(ord('a'), ord('z') + 1)] +
    [chr(c) for c in range(ord('1'), ord('9') + 1)] +
    ['0', '-']
)

def roland_checksum(data):
    return sum(-b for b in data) & 0x7F

def address_to_index(addr):
    return addr[2] + (addr[1] << 7) + (addr[0] << 14)

def is_d50_sysex(msg):
    return (len(msg) > 4 and
            msg[0] == 0xF0 and
            msg[1] == ROLAND_ID and
            msg[3] == MODEL_ID)

def parse_roland_message(msg):
    if not is_d50_sysex(msg):
        return None, None, None
    body = msg[5:-2]
    checksum = msg[-2]
    if roland_checksum(body) != checksum:
        raise ValueError("Checksum error in SysEx message")
    command = msg[4]
    address = list(msg[5:8])
    data = list(msg[8:-2])
    return command, address, data

def split_sysex(raw_bytes):
    messages = []
    i = 0
    length = len(raw_bytes)
    while i < length:
        if raw_bytes[i] == 0xF0:
            start = i
            while i < length and raw_bytes[i] != 0xF7:
                i += 1
            if i < length:
                messages.append(list(raw_bytes[start:i+1]))
                i += 1
            else:
                break
        else:
            i += 1
    return messages

def decode_name(data, length=18):
    name = []
    for b in data[:length]:
        if 0 <= b < len(CHARSET):
            name.append(CHARSET[b])
        else:
            name.append('?')
    return ''.join(name).rstrip()

def load_d50_sysex(raw_bytes):
    """Load a classic Roland D-50/D-550 SysEx bulk dump."""
    messages = split_sysex(raw_bytes)
    if not messages:
        raise ValueError("No SysEx messages found in file")

    max_addr = address_to_index([0x04, 0x0C, 0x08]) + 400
    ram = [0xFF] * max_addr

    for msg in messages:
        try:
            cmd, addr, data = parse_roland_message(msg)
            if cmd == CMD_DT1 and addr is not None:
                base = address_to_index(addr)
                end = base + len(data)
                if end <= len(ram):
                    ram[base:end] = data
        except Exception:
            continue

    patch_names = []
    patch_base_index = address_to_index([0x02, 0x00, 0x00])

    for p in range(64):
        name_offset = patch_base_index + p * (7 * 0x40) + 0x180
        name_data = ram[name_offset : name_offset + 18]
        name = decode_name(name_data, 18)
        patch_names.append(name if name else f"(empty {p+1})")

    return patch_names

# ---------------------------------------------------------------------------
# D-50 VSTi / Roland Cloud .bin (KoaBankFile) support
# ---------------------------------------------------------------------------

KOA_HEADER = b"KoaBankFile"
BIN_NAME_OFFSET = 22          # first patch name starts right after the header
BIN_PATCH_STRIDE = 468        # each patch occupies 468 bytes
BIN_NAME_LENGTH = 18

def is_koa_bin(raw_bytes):
    return raw_bytes.startswith(KOA_HEADER)

def load_d50_bin(raw_bytes):
    """
    Load a D-50 VSTi / Roland Cloud .bin bank (KoaBankFile format).

    Structure observed:
      - Header: "KoaBankFile00003PG-D50" (22 bytes)
      - 64 patches × 468 bytes each
      - Patch name (18 chars, space-padded) is at the start of every 468-byte block
    """
    if not is_koa_bin(raw_bytes):
        raise ValueError("Not a KoaBankFile (.bin) bank")

    if len(raw_bytes) < BIN_NAME_OFFSET + BIN_PATCH_STRIDE:
        raise ValueError("File too small to be a valid D-50 .bin bank")

    patch_names = []
    for p in range(64):
        offset = BIN_NAME_OFFSET + p * BIN_PATCH_STRIDE
        if offset + BIN_NAME_LENGTH > len(raw_bytes):
            patch_names.append(f"(missing {p+1})")
            continue

        name_bytes = raw_bytes[offset : offset + BIN_NAME_LENGTH]
        try:
            # Names are stored as plain ASCII (not the Roland charset)
            name = name_bytes.decode("ascii", errors="replace").rstrip("\x00 ").rstrip()
        except Exception:
            name = ""

        patch_names.append(name if name else f"(empty {p+1})")

    return patch_names

def load_d50_bank(raw_bytes):
    """Auto-detect format and load patch names."""
    if is_koa_bin(raw_bytes):
        return load_d50_bin(raw_bytes)
    else:
        return load_d50_sysex(raw_bytes)

# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class D50BankReaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Roland D-50 Bank Reader (SysEx + VSTi .bin)")
        self.geometry("720x580")
        self.minsize(520, 420)

        self.current_names = []          # stores the last loaded names
        self.current_filename = ""

        self.create_widgets()

    def create_widgets(self):
        # ---- Top bar ----
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Bank file:").pack(side=tk.LEFT)

        self.file_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.file_var, width=55)
        entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        ttk.Button(top, text="Browse…", command=self.browse_and_load).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Export to TXT…", command=self.export_txt).pack(side=tk.LEFT, padx=2)

        # ---- Status bar ----
        self.status_var = tk.StringVar(value="Ready – select a Roland D-50 .syx or .bin bank file")
        ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)\
            .pack(side=tk.BOTTOM, fill=tk.X)

        # ---- Treeview ----
        list_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("#", "Patch Name")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=22)
        self.tree.heading("#", text="#")
        self.tree.heading("Patch Name", text="Patch Name")
        self.tree.column("#", width=50, anchor=tk.CENTER)
        self.tree.column("Patch Name", width=520, anchor=tk.W)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(self, text="Supports SysEx bulk dumps (≈ 36 048 bytes) and D-50 VSTi .bin banks (KoaBankFile). "
                             "64 patches expected.",
                  padding=5).pack()

    def browse_and_load(self):
        path = filedialog.askopenfilename(
            title="Select Roland D-50 bank file",
            filetypes=[
                ("D-50 banks", "*.syx *.bin"),
                ("SysEx files", "*.syx"),
                ("VSTi / Roland Cloud bins", "*.bin"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return

        self.file_var.set(path)
        self.load_file(path)

    def load_file(self, path):
        if not os.path.isfile(path):
            messagebox.showerror("Error", f"File not found:\n{path}")
            return

        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as e:
            messagebox.showerror("Read error", str(e))
            return

        self.status_var.set(f"Loading {os.path.basename(path)} ({len(raw)} bytes)…")
        self.update_idletasks()

        try:
            names = load_d50_bank(raw)
        except Exception as e:
            messagebox.showerror("Parse error", f"Could not parse the file:\n{e}")
            self.status_var.set("Error while parsing")
            self.current_names = []
            return

        # Clear previous results
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, name in enumerate(names, start=1):
            self.tree.insert("", tk.END, values=(f"{i:02d}", name))

        self.current_names = names
        self.current_filename = os.path.basename(path)

        fmt = "VSTi .bin" if is_koa_bin(raw) else "SysEx"
        self.status_var.set(f"Loaded {len(names)} patches from {self.current_filename} ({fmt})")

    def export_txt(self):
        if not self.current_names:
            messagebox.showwarning("Nothing to export", "Please load a bank file first.")
            return

        # Suggest a default name based on the original file
        default_name = os.path.splitext(self.current_filename)[0] + "_patches.txt"

        path = filedialog.asksaveasfilename(
            title="Export patch list",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Roland D-50 Patch List\n")
                f.write(f"Source: {self.current_filename}\n")
                f.write("=" * 40 + "\n\n")
                for i, name in enumerate(self.current_names, start=1):
                    f.write(f"{i:02d}  {name}\n")
            self.status_var.set(f"Exported to {os.path.basename(path)}")
            messagebox.showinfo("Export successful", f"Patch list saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = D50BankReaderApp()
    app.mainloop()