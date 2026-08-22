import os
import random
import math
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

PREFIXES_80S = [
    "NEON", "CYBER", "SOLAR", "RETRO", "COSMIC", "LASER", "CHROME", "VELVET",
    "ANALOG", "CRYSTAL", "FUTURE", "TURBO", "PLASMA", "VECTOR", "ASTRAL", "SHADOW",
    "MIDNIGHT", "SYNTH", "HYPER", "KINETIC", "ARCADIA", "VORTEX", "DIGITAL", "SILVER",
    "ALPHA", "OMEGA", "KRONOS", "TITAN", "STELLAR", "NEBULA", "GALACTIC", "ORION",
    "PULSE", "MODULAR", "ELECTRO", "SPECTRA", "POLARIS", "AURORA", "VAPOR", "TECHNO",
    "SONIC", "NEXUS", "ZENITH", "AERO", "LUNAR", "VOYAGER", "PHANTOM", "MATRIX", "QUANTUM",
    "HELIOS", "HORIZON", "INFINITY", "MAGNETIC", "OBSIDIAN", "RADIANT", "SAPPHIRE"
]

NOUNS_80S = [
    "DREAMS", "RUNNER", "PULSE", "WAVE", "MATRIX", "HORIZON", "BLASTER", "NIGHTS",
    "STRIDER", "FORCE", "ECHO", "VOYAGER", "ORBIT", "BEAM", "RIDER", "AURORA",
    "QUEST", "HAZE", "PHANTOM", "VOX", "ZONE", "MIRAGE", "HEAVEN", "GLIDE",
    "FLIGHT", "STORM", "SHIFT", "DRIFT", "GHOST", "CHORD", "PAD", "LEAD", "BASS",
    "BELLS", "KEYS", "BRASS", "STRINGS", "SWEEP", "ATMOSPHERE", "VOICE", "CHOIR"
]

SUFFIXES_80S = [
    "80", "84", "88", "99", "2000", "3000", "X", "XL", "FX", "DX", "LA",
    "MK2", "MK3", "PRO", "PLUS", "MAX", "ONE", "ZERO", "II", "III", "IV", "V",
    "EX", "HD", "TX", "JX", "VP", "D50", "D550", "V1", "V2", "3D", "HQ"
]

# Jeu de caractères officiel Roland D-50 (indices 0-63)
D50_CHARSET = (
    [' '] +
    [chr(c) for c in range(ord('A'), ord('Z') + 1)] +
    [chr(c) for c in range(ord('a'), ord('z') + 1)] +
    [chr(c) for c in range(ord('1'), ord('9') + 1)] +
    ['0', '-']
)
D50_CHAR_TO_BYTE = {c: i for i, c in enumerate(D50_CHARSET)}


class RotaryKnob(tk.Canvas):
    def __init__(self, parent, size=75, min_val=0, max_val=100, initial_val=25, command=None, bg="#2B2C34"):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0)
        self.size = size
        self.min_val = min_val
        self.max_val = max_val
        self.val = initial_val
        self.command = command
        self.last_y = 0

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._change_val(1))
        self.bind("<Button-5>", lambda e: self._change_val(-1))

        self.draw()

    def _on_press(self, event):
        self.last_y = event.y

    def _on_motion(self, event):
        dy = self.last_y - event.y
        self.last_y = event.y
        if dy != 0:
            self._change_val(dy)

    def _on_wheel(self, event):
        delta = 1 if event.delta > 0 else -1
        self._change_val(delta)

    def _change_val(self, delta):
        old_val = self.val
        self.val = max(self.min_val, min(self.max_val, self.val + delta))
        if self.val != old_val:
            self.draw()
            if self.command:
                self.command(self.val)

    def get(self):
        return self.val

    def set(self, val):
        self.val = max(self.min_val, min(self.max_val, val))
        self.draw()

    def draw(self):
        self.delete("all")
        cx = self.size / 2
        cy = self.size / 2
        r = (self.size / 2) - 6

        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#18191D", outline="#44475A", width=2)
        self.create_oval(cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5, fill="#25262C", outline="#111215", width=1)

        angle_deg = -135 + (self.val - self.min_val) / (self.max_val - self.min_val) * 270
        angle_rad = math.radians(angle_deg)

        indicator_r1 = r - 16
        indicator_r2 = r - 4
        x1 = cx + indicator_r1 * math.sin(angle_rad)
        y1 = cy - indicator_r1 * math.cos(angle_rad)
        x2 = cx + indicator_r2 * math.sin(angle_rad)
        y2 = cy - indicator_r2 * math.cos(angle_rad)

        line_color = "#FF3333" if self.val > 40 else "#50FFB1"

        self.create_line(x1, y1, x2, y2, fill=line_color, width=3, capstyle="round")
        self.create_text(cx, cy, text=f"{int(self.val)}%", font=("Helvetica", 9, "bold"), fill="#EAEAEA")


class LAMApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LAM - Roland D-50 Bank Generator")
        self.root.geometry("780x790")
        self.root.resizable(False, False)

        self.bg_color = "#1E1E24"
        self.panel_color = "#2B2C34"
        self.lcd_bg = "#1B4D3E"
        self.lcd_fg = "#50FFB1"
        self.accent_red = "#D64045"
        self.accent_blue = "#4EA5D9"
        self.btn_color = "#3A3D4A"

        self.root.configure(bg=self.bg_color)

        self.loaded_sysex = None
        self.loaded_filename = ""

        self.force_pure_analog = tk.BooleanVar(value=False)
        self.lock_structures = tk.BooleanVar(value=False)
        self.lock_pitch = tk.BooleanVar(value=False)
        self.lock_tva = tk.BooleanVar(value=False)
        self.lock_tvf = tk.BooleanVar(value=False)
        self.lock_lfo = tk.BooleanVar(value=False)
        self.lock_eq = tk.BooleanVar(value=False)
        self.lock_bpc = tk.BooleanVar(value=False)
        self.lock_fx = tk.BooleanVar(value=False)

        self._setup_styles()
        self._build_header()

        self.main_frame = tk.Frame(self.root, bg=self.bg_color)
        self.main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._build_mutator_panel(self.main_frame)
        self._build_footer()

        self._update_lcd_display()
        self.log("LAM initialized. Ready to load Roland D-50 SysEx data.")

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

    def _build_header(self):
        header = tk.Frame(self.root, bg=self.bg_color, height=50)
        header.pack(fill="x", padx=15, pady=8)

        title = tk.Label(header, text="LAM", font=("Helvetica", 20, "bold"), fg="#EAEAEA", bg=self.bg_color)
        title.pack(side="left")

        subtitle = tk.Label(header, text="LINEAR ARITHMETIC SYNTHESIS BANK MUTATOR",
                            font=("Helvetica", 8, "bold"), fg=self.accent_blue, bg=self.bg_color)
        subtitle.pack(side="left", padx=15, pady=(8, 0))

    def _build_mutator_panel(self, parent):
        self._build_lcd_display(parent)
        self._build_algorithm_panel(parent)
        self._build_parameter_locks_panel(parent)
        self._build_export_settings_panel(parent)
        self._build_knob_and_action_controls(parent)
        self._build_log_console(parent)

    def _build_lcd_display(self, parent):
        lcd_frame = tk.Frame(parent, bg="#0D0E11", bd=2, relief="sunken")
        lcd_frame.pack(fill="x", padx=10, pady=2)

        self.lcd = tk.Frame(lcd_frame, bg=self.lcd_bg, bd=6)
        self.lcd.pack(fill="both", expand=True)

        tk.Label(self.lcd, text="IMPORTED BANK  :", font=("Courier", 9, "bold"),
                 fg=self.lcd_fg, bg=self.lcd_bg).grid(row=0, column=0, sticky="w", pady=1)
        self.lbl_imported = tk.Label(self.lcd, text="[ NO FILE LOADED ]", font=("Courier", 10, "bold"),
                                     fg="#A3FFD6", bg=self.lcd_bg)
        self.lbl_imported.grid(row=0, column=1, sticky="w", pady=1)

        tk.Label(self.lcd, text="MUTATION MODE :", font=("Courier", 9, "bold"),
                 fg=self.lcd_fg, bg=self.lcd_bg).grid(row=1, column=0, sticky="w", pady=1)
        self.lbl_lcd_mode = tk.Label(self.lcd, text="STANDARD", font=("Courier", 10, "bold"),
                                     fg="#A3FFD6", bg=self.lcd_bg)
        self.lbl_lcd_mode.grid(row=1, column=1, sticky="w", pady=1)

        tk.Label(self.lcd, text="MUTATION RATE :", font=("Courier", 9, "bold"),
                 fg=self.lcd_fg, bg=self.lcd_bg).grid(row=2, column=0, sticky="w", pady=1)
        self.lbl_lcd_rand = tk.Label(self.lcd, text="[█████...............] 25%", font=("Courier", 10, "bold"),
                                     fg=self.lcd_fg, bg=self.lcd_bg)
        self.lbl_lcd_rand.grid(row=2, column=1, sticky="w", pady=1)

        tk.Label(self.lcd, text="LOCKED PARAMS :", font=("Courier", 9, "bold"),
                 fg=self.lcd_fg, bg=self.lcd_bg).grid(row=3, column=0, sticky="w", pady=1)
        self.lbl_lcd_locks = tk.Label(self.lcd, text="[ AUTO-NAME ]", font=("Courier", 9, "bold"),
                                      fg="#A3FFD6", bg=self.lcd_bg)
        self.lbl_lcd_locks.grid(row=3, column=1, sticky="w", pady=1)

        tk.Label(self.lcd, text="EXPORT PREFIX :", font=("Courier", 9, "bold"),
                 fg=self.lcd_fg, bg=self.lcd_bg).grid(row=4, column=0, sticky="w", pady=1)
        self.lbl_lcd_prefix = tk.Label(self.lcd, text="LAM_MUTATED", font=("Courier", 10, "bold"),
                                       fg="#A3FFD6", bg=self.lcd_bg)
        self.lbl_lcd_prefix.grid(row=4, column=1, sticky="w", pady=1)

    def _build_algorithm_panel(self, parent):
        algo_frame = tk.LabelFrame(parent, text=" MUTATION ALGORITHM & NAMING ",
                                   font=("Helvetica", 8, "bold"), fg="#AAAAAA",
                                   bg=self.panel_color, bd=2, relief="groove")
        algo_frame.pack(fill="x", padx=10, pady=4)
        algo_frame.columnconfigure(1, weight=1)

        tk.Label(algo_frame, text="Algorithm Mode:", font=("Helvetica", 9, "bold"),
                 fg="#EAEAEA", bg=self.panel_color).grid(row=0, column=0, padx=10, pady=4, sticky="w")

        self.algo_var = tk.StringVar(value="Standard")
        combo_algo = ttk.Combobox(algo_frame, textvariable=self.algo_var,
                                  values=["Standard", "Drift", "Mirror", "Chaos"],
                                  state="readonly", width=22)
        combo_algo.grid(row=0, column=1, padx=5, pady=4, sticky="w")
        combo_algo.bind("<<ComboboxSelected>>", lambda e: self._update_lcd_display())

        self.gen_names_var = tk.BooleanVar(value=True)
        chk_gen_names = tk.Checkbutton(algo_frame, text="Auto generate preset names",
                                       variable=self.gen_names_var, font=("Helvetica", 8, "bold"),
                                       fg="#A3FFD6", bg=self.panel_color,
                                       activebackground=self.panel_color, activeforeground="#A3FFD6",
                                       selectcolor="#15161A", command=self._update_lcd_display)
        chk_gen_names.grid(row=0, column=2, padx=10, pady=4, sticky="e")

    def _build_parameter_locks_panel(self, parent):
        locks_frame = tk.LabelFrame(parent, text=" PARAMETER LOCKS & GENERATION OVERRIDES ",
                                    font=("Helvetica", 8, "bold"), fg="#AAAAAA",
                                    bg=self.panel_color, bd=2, relief="groove")
        locks_frame.pack(fill="x", padx=10, pady=4)
        locks_frame.columnconfigure((0, 1), weight=1)

        chk_pure_analog = tk.Checkbutton(locks_frame, text="⚡ FORCE PURE ANALOG",
                                         variable=self.force_pure_analog, font=("Helvetica", 8, "bold"),
                                         fg="#FFD700", bg=self.panel_color,
                                         activebackground=self.panel_color, activeforeground="#FFD700",
                                         selectcolor="#15161A", command=self._update_lcd_display)
        chk_pure_analog.grid(row=0, column=0, columnspan=2, padx=10, pady=4, sticky="w")

        locks_cfg = [
            ("1- STRUCTURES PARAMETERS", self.lock_structures, 1, 0),
            ("2- PITCH PARAMETERS", self.lock_pitch, 1, 1),
            ("3- TVA PARAMETERS", self.lock_tva, 2, 0),
            ("4- TVF PARAMETERS", self.lock_tvf, 2, 1),
            ("5- LFO PARAMETERS", self.lock_lfo, 3, 0),
            ("6- EQ PARAMETERS", self.lock_eq, 3, 1),
            ("7- BEND, PORTAMENTO & CHASE", self.lock_bpc, 4, 0),
            ("8- FX PARAMETERS", self.lock_fx, 4, 1)
        ]

        for text, var, row, col in locks_cfg:
            chk = tk.Checkbutton(locks_frame, text=text, variable=var, font=("Helvetica", 8),
                                 fg="#EAEAEA", bg=self.panel_color,
                                 activebackground=self.panel_color, activeforeground="#EAEAEA",
                                 selectcolor="#15161A", command=self._update_lcd_display)
            chk.grid(row=row, column=col, padx=10, pady=2, sticky="w")

    def _build_export_settings_panel(self, parent):
        settings_frame = tk.LabelFrame(parent, text=" BANK EXPORT CONFIGURATION ",
                                       font=("Helvetica", 8, "bold"), fg="#AAAAAA",
                                       bg=self.panel_color, bd=2, relief="groove")
        settings_frame.pack(fill="x", padx=10, pady=4)

        tk.Label(settings_frame, text="Export Prefix Name:", font=("Helvetica", 8, "bold"),
                 fg="#EAEAEA", bg=self.panel_color).grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.prefix_var = tk.StringVar(value="LAM_MUTATED")
        self.prefix_var.trace_add("write", lambda *args: self._update_lcd_display())

        self.entry_export_prefix = tk.Entry(settings_frame, textvariable=self.prefix_var,
                                            font=("Helvetica", 9), bg="#15161A", fg="#FFFFFF",
                                            insertbackground="white", bd=1, relief="solid", width=20)
        self.entry_export_prefix.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        tk.Label(settings_frame, text="Number of Banks:", font=("Helvetica", 8, "bold"),
                 fg="#EAEAEA", bg=self.panel_color).grid(row=0, column=2, padx=(20, 5), pady=5, sticky="w")

        self.spin_count = tk.Spinbox(settings_frame, from_=1, to=99, width=5,
                                     font=("Helvetica", 9, "bold"), bg="#15161A", fg="#FFFFFF",
                                     buttonbackground=self.btn_color, bd=1, relief="solid")
        self.spin_count.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self.spin_count.delete(0, "end")
        self.spin_count.insert(0, "1")

    def _build_knob_and_action_controls(self, parent):
        panel = tk.Frame(parent, bg=self.panel_color, bd=2, relief="groove")
        panel.pack(fill="x", padx=10, pady=6)
        panel.columnconfigure((0, 1, 2), weight=1)

        btn_import = tk.Button(panel, text="LOAD SYSEX BANK", font=("Helvetica", 10, "bold"),
                               bg=self.btn_color, fg="white", activebackground=self.accent_blue,
                               bd=2, relief="raised", height=2, command=self.load_sysex)
        btn_import.grid(row=0, column=0, padx=20, pady=10, sticky="ew")

        knob_container = tk.Frame(panel, bg=self.panel_color)
        knob_container.grid(row=0, column=1, pady=6)

        tk.Label(knob_container, text="MUTATION AMOUNT", font=("Helvetica", 8, "bold"),
                 fg="#AAAAAA", bg=self.panel_color).pack(anchor="center", pady=(0, 2))

        self.knob_rand = RotaryKnob(knob_container, size=80, min_val=0, max_val=100,
                                    initial_val=25, command=self._update_lcd_rand, bg=self.panel_color)
        self.knob_rand.pack(anchor="center")

        btn_generate = tk.Button(panel, text="GENERATE BANKS", font=("Helvetica", 10, "bold"),
                                 bg=self.accent_red, fg="white", activebackground="#B33035",
                                 bd=2, relief="raised", height=2, command=self.generate_banks)
        btn_generate.grid(row=0, column=2, padx=20, pady=10, sticky="ew")

    def _build_log_console(self, parent):
        log_frame = tk.Frame(parent, bg=self.bg_color)
        log_frame.pack(fill="x", padx=10, pady=4)

        title_frame = tk.Frame(log_frame, bg=self.bg_color)
        title_frame.pack(fill="x", pady=(0, 1))

        tk.Label(title_frame, text="SYSTEM LOG / DATA ACTIVITY", font=("Helvetica", 8, "bold"),
                 fg="#888888", bg=self.bg_color).pack(side="left")

        console_frame = tk.Frame(log_frame, bg="#0A0A0C", bd=2, relief="sunken")
        console_frame.pack(fill="x")

        self.txt_log = tk.Text(console_frame, bg="#0A0A0C", fg="#33FF77", font=("Consolas", 8),
                               bd=0, highlightthickness=0, wrap="word", height=5, state="disabled")
        scrollbar = tk.Scrollbar(console_frame, command=self.txt_log.yview, bg="#1E1E24")

        self.txt_log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True, padx=4, pady=2)

    def _build_footer(self):
        footer = tk.Frame(self.root, bg=self.bg_color)
        footer.pack(fill="x", padx=15, pady=2)

        self.status_lbl = tk.Label(footer, text="STATUS: Ready - Load Roland D-50 .syx file",
                                   font=("Helvetica", 8), fg="#777777", bg=self.bg_color)
        self.status_lbl.pack(side="left")

    def log(self, message):
        timestamp = time.strftime("[%H:%M:%S]")
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", f"{timestamp} {message}\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def _update_lcd_rand(self, val):
        pct = int(float(val))
        bars = int((pct / 100) * 20)
        self.lbl_lcd_rand.config(text="[" + "█" * bars + "." * (20 - bars) + f"] {pct}%")

    def _update_lcd_display(self):
        mode_str = self.algo_var.get().upper()
        if self.force_pure_analog.get():
            mode_str += " [PURE ANALOG]"
        self.lbl_lcd_mode.config(text=mode_str)

        locks = []
        if self.force_pure_analog.get(): locks.append("PURE-ANALOG")
        if self.gen_names_var.get(): locks.append("NAME")
        if self.lock_structures.get(): locks.append("STRUCT")
        if self.lock_pitch.get(): locks.append("PITCH")
        if self.lock_tva.get(): locks.append("TVA")
        if self.lock_tvf.get(): locks.append("TVF")
        if self.lock_lfo.get(): locks.append("LFO")
        if self.lock_eq.get(): locks.append("EQ")
        if self.lock_bpc.get(): locks.append("BEND/PORTA")
        if self.lock_fx.get(): locks.append("FX")

        locks_str = "+".join(locks) if locks else "NONE"
        if len(locks_str) > 22:
            locks_str = locks_str[:19] + "..."
        self.lbl_lcd_locks.config(text=f"[ {locks_str} ]")

        prefix_str = self.prefix_var.get().strip() or "LAM"
        disp_prefix = prefix_str if len(prefix_str) <= 24 else prefix_str[:21] + "..."
        self.lbl_lcd_prefix.config(text=disp_prefix)

    def load_sysex(self):
        file_path = filedialog.askopenfilename(
            title="Select Roland D-50 SysEx Bank",
            filetypes=[("SysEx Files", "*.syx"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "rb") as f:
                data = f.read()

            if len(data) == 0:
                self.log("ERROR: Selected file is empty.")
                messagebox.showerror("Error", "The selected file is empty.")
                return

            self.loaded_sysex = bytearray(data)
            self.loaded_filename = os.path.basename(file_path)

            disp_name = self.loaded_filename if len(self.loaded_filename) <= 22 else self.loaded_filename[:19] + "..."
            self.lbl_imported.config(text=disp_name.upper())
            self.status_lbl.config(text=f"STATUS: Loaded '{self.loaded_filename}' ({len(data)} bytes).")
            self.log(f"FILE LOADED: '{self.loaded_filename}' | Size: {len(data)} bytes")

        except Exception as e:
            self.log(f"ERROR: Failed to read file -> {str(e)}")
            messagebox.showerror("Error", f"Failed to read file:\n{str(e)}")

    def _encode_d50_name(self, text, length):
        """Encode une chaîne en octets D-50 (indices 0-63)."""
        text = text.upper()[:length].ljust(length, ' ')
        result = []
        for c in text:
            if c in D50_CHAR_TO_BYTE:
                result.append(D50_CHAR_TO_BYTE[c])
            else:
                result.append(0)  # espace
        return result

    def _generate_80s_patch_name(self, length=18):
        """Génère un nom style 80s et l'encode correctement pour le D-50."""
        r = random.random()
        if r < 0.35:
            raw = f"{random.choice(PREFIXES_80S)} {random.choice(NOUNS_80S)}"
        elif r < 0.65:
            word = random.choice(NOUNS_80S if random.random() > 0.5 else PREFIXES_80S)
            raw = f"{word} {random.choice(SUFFIXES_80S)}"
        elif r < 0.85:
            raw = f"{random.choice(PREFIXES_80S)}{random.choice(SUFFIXES_80S)}"
        else:
            raw = random.choice(NOUNS_80S)
        return self._encode_d50_name(raw, length)

    def _mutate_byte(self, original_val, rate, algo_mode):
        if random.random() > rate:
            return original_val

        if algo_mode == "Drift":
            delta = int(random.gauss(0, 5 * rate))
            new_val = original_val + delta
        elif algo_mode == "Mirror":
            new_val = 127 - original_val
        elif algo_mode == "Chaos":
            new_val = random.randint(0, 127)
        else:
            delta = int(random.gauss(0, 32 * rate))
            new_val = original_val + delta

        return max(0, min(127, new_val))

    def _calculate_roland_checksum(self, data_bytes):
        """Checksum standard Roland : 128 - (somme % 128)."""
        total = sum(data_bytes)
        return (128 - (total % 128)) & 0x7F

    def _partial_local_offset(self, offset_in_patch):
        """
        Si offset_in_patch est dans un des 4 partials, retourne l'offset local 0-53.
        Sinon retourne None.
        Partials :
          Upper P1: 0-53
          Upper P2: 64-117
          Lower P1: 192-245
          Lower P2: 256-309
        """
        for base in (0, 64, 192, 256):
            if base <= offset_in_patch <= base + 53:
                return offset_in_patch - base
        return None

    def _is_byte_locked(self, offset_in_patch):
        """
        Détermine si un octet (offset relatif dans le patch 0-447) doit être figé.

        Mapping D-50 (patch 448 octets) :
          Partials (x4) local 0-53 :
            0-5   Pitch (Coarse, Fine, KF, Mod LFO/P-ENV/Bender)
            6-12  Waveform / PCM / Pulse Width (+ mods)
            13-34 TVF (+ ENV + Mod)
            35-53 TVA (+ ENV + Mod)
          Common Upper 128-175 / Lower 320-367 :
            +10   Structure No.          -> 138 / 330
            +11..24  P-ENV + Pitch Mod  -> 139-152 / 331-344
            +25..36  LFO 1/2/3          -> 153-164 / 345-356
            +37..41  EQ                 -> 165-169 / 357-361
            +42..45  Chorus (FX tone)   -> 170-173 / 362-365
            +46..47  Partial Mute/Bal   -> 174-175 / 366-367
          Patch 384-420+ :
            +18   Key Mode              -> 402
            +19   Split Point           -> 403
            +20..21 Portamento/Hold     -> 404-405
            +22..25 Key/Fine Shift      -> 406-409
            +26..27 Bender / After Bend -> 410-411
            +28..  Chase, Output, Reverb, Volume...
        """
        # --- Partials (Pitch / TVF / TVA) ---
        p_off = self._partial_local_offset(offset_in_patch)
        if p_off is not None:
            if self.lock_pitch.get() and 0 <= p_off <= 5:
                return True
            if self.lock_tvf.get() and 13 <= p_off <= 34:
                return True
            if self.lock_tva.get() and 35 <= p_off <= 53:
                return True
            # LFO-related modulation sources inside partial
            if self.lock_lfo.get() and p_off in (3, 10, 11, 32, 33):
                return True
            return False

        # --- Common Upper (128-175) / Lower (320-367) ---
        for common_base in (128, 320):
            if common_base <= offset_in_patch <= common_base + 47:
                rel = offset_in_patch - common_base  # 0 = first name char, 10 = Structure
                if self.lock_structures.get() and rel == 10:
                    return True
                # P-ENV + Pitch Mod (indices 11-24)
                if self.lock_pitch.get() and 11 <= rel <= 24:
                    return True
                # LFO 1/2/3 (indices 25-36)
                if self.lock_lfo.get() and 25 <= rel <= 36:
                    return True
                # EQ (indices 37-41)
                if self.lock_eq.get() and 37 <= rel <= 41:
                    return True
                # Chorus / tone FX (indices 42-45)
                if self.lock_fx.get() and 42 <= rel <= 45:
                    return True
                # Partial Mute / Balance → lié aux structures
                if self.lock_structures.get() and 46 <= rel <= 47:
                    return True
                return False

        # --- Patch factors (384+) ---
        if offset_in_patch >= 384:
            rel = offset_in_patch - 384  # 0 = first name char, 18 = Key Mode
            # Bend, Portamento, Hold, Key shifts, Aftertouch bend
            if self.lock_bpc.get() and rel in (
                20, 21,           # Portamento Mode, Hold Mode
                22, 23, 24, 25,  # Key Shift U/L, Fine Tune U/L
                26, 27,          # Bender Range, After Bend Range
            ):
                return True
            # Output Mode / Reverb / Chase / Total Volume (approx 28+)
            if self.lock_fx.get() and rel >= 28:
                return True
            return False

        return False

    def _addr_to_index(self, ah, am, al):
        """Convertit adresse Roland 3 octets en index linéaire."""
        return (ah << 14) + (am << 7) + al

    def _is_name_offset_in_patch(self, offset_in_patch):
        """
        Dans un patch de 448 octets :
          128-137  = Upper Tone name (10)
          320-329  = Lower Tone name (10)
          384-401  = Patch name (18)
        """
        if 128 <= offset_in_patch <= 137:
            return "tone", 10, offset_in_patch - 128
        if 320 <= offset_in_patch <= 329:
            return "tone", 10, offset_in_patch - 320
        if 384 <= offset_in_patch <= 401:
            return "patch", 18, offset_in_patch - 384
        return None, 0, 0

    def generate_banks(self):
        if not self.loaded_sysex:
            self.log("ERROR: Generation aborted. No SysEx file loaded.")
            messagebox.showerror("Error", "Please load a Roland D-50 SysEx file first.")
            return

        messages = []
        i = 0
        n = len(self.loaded_sysex)
        while i < n:
            if self.loaded_sysex[i] == 0xF0:
                j = i
                while j < n and self.loaded_sysex[j] != 0xF7:
                    j += 1
                if j < n and self.loaded_sysex[j] == 0xF7:
                    messages.append((i, j))
                    i = j
            i += 1

        if not messages:
            self.log("ERROR: Invalid SysEx file structure (no F0...F7 frames).")
            messagebox.showerror("Format Error", "Aucun message SysEx valide (F0...F7) trouvé.")
            return

        export_dir = filedialog.askdirectory(title="Select Output Directory")
        if not export_dir:
            return

        prefix = self.prefix_var.get().strip() or "LAM"
        rate = float(self.knob_rand.get()) / 100.0
        algo_mode = self.algo_var.get()
        gen_names = self.gen_names_var.get()
        pure_analog = self.force_pure_analog.get()
        count = int(self.spin_count.get())

        PATCH_SIZE = 448
        WORK_AREA_BASE = 0x8000  # adresse 02 00 00

        created_files = 0
        for b_idx in range(1, count + 1):
            mutated = bytearray(self.loaded_sysex)

            # Cache des noms par patch pour cohérence
            name_cache = {}  # patch_index -> (patch_name_18, upper_10, lower_10)

            for start, end in messages:
                if end - start < 10:
                    continue
                if not (mutated[start + 1] == 0x41 and mutated[start + 3] == 0x14 and mutated[start + 4] == 0x12):
                    continue

                addr_high = mutated[start + 5]
                addr_mid = mutated[start + 6]
                addr_low = mutated[start + 7]
                data_start = start + 8
                checksum_pos = end - 1

                base_index = self._addr_to_index(addr_high, addr_mid, addr_low)

                for d_idx in range(data_start, checksum_pos):
                    abs_index = base_index + (d_idx - data_start)

                    # On ne traite que la zone patch memory
                    if abs_index < WORK_AREA_BASE:
                        continue

                    offset_from_work = abs_index - WORK_AREA_BASE
                    patch_index = offset_from_work // PATCH_SIZE
                    offset_in_patch = offset_from_work % PATCH_SIZE

                    name_kind, name_len, name_pos = self._is_name_offset_in_patch(offset_in_patch)

                    if name_kind is not None:
                        # C'est un octet de nom
                        if gen_names:
                            if patch_index not in name_cache:
                                name_cache[patch_index] = (
                                    self._generate_80s_patch_name(18),
                                    self._generate_80s_patch_name(10),
                                    self._generate_80s_patch_name(10)
                                )
                            p_name, u_name, l_name = name_cache[patch_index]

                            if name_kind == "patch":
                                mutated[d_idx] = p_name[name_pos]
                            else:  # tone
                                if 128 <= offset_in_patch <= 137:
                                    mutated[d_idx] = u_name[name_pos]
                                else:
                                    mutated[d_idx] = l_name[name_pos]
                        # Si gen_names = False → on laisse le nom original intact
                        continue

                    # Force Pure Analog : Structure No. = 0 (Structure 1 = S+S, pas de PCM)
                    # Offsets Structure dans le patch : Upper Common +10 = 138, Lower Common +10 = 330
                    if pure_analog and offset_in_patch in (138, 330):
                        mutated[d_idx] = 0  # Structure 1 = Synthesizer + Synthesizer
                        continue

                    # Pas un octet de nom → mutation normale (sauf locks)
                    if self._is_byte_locked(offset_in_patch):
                        continue

                    old_b = mutated[d_idx]
                    mutated[d_idx] = self._mutate_byte(old_b, rate, algo_mode)

                # Recalcul du checksum Roland
                addr_and_data = mutated[start + 5:checksum_pos]
                mutated[checksum_pos] = self._calculate_roland_checksum(addr_and_data)

            filename = f"{prefix}_{b_idx:02d}.syx"
            with open(os.path.join(export_dir, filename), "wb") as f:
                f.write(mutated)

            created_files += 1

        self.log(f"SUCCESS: {created_files} bank(s) saved to {export_dir}")
        messagebox.showinfo("Success", f"{created_files} banque(s) générée(s) avec succès.")


if __name__ == "__main__":
    root = tk.Tk()
    app = LAMApp(root)
    root.mainloop()