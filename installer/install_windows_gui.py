"""Kwyre AI — Windows One-Click GUI Installer (tkinter)"""

import ctypes
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import winreg

VERSION = "1.0.0"
APP_NAME = "Kwyre AI"
DEFAULT_INSTALL_DIR = os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\User"), "kwyre")
SCRIPT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLORS = {
    "bg": "#0b0d14",
    "bg_light": "#131620",
    "bg_card": "#181c28",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "green": "#22c55e",
    "red": "#ef4444",
    "text": "#e2e4ea",
    "text_dim": "#8b8fa3",
    "border": "#262b3a",
}

MIT_LICENSE = """\
MIT License

Copyright (c) 2025 Brain-inspired computing lab

Permission is hereby granted, free of charge, to any person obtaining a copy \
of this software and associated documentation files (the "Software"), to deal \
in the Software without restriction, including without limitation the rights \
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell \
copies of the Software, and to permit persons to whom the Software is \
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all \
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR \
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, \
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE \
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER \
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, \
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE \
SOFTWARE.
"""


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def request_admin():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)


class KwyreInstaller(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Kwyre AI Installer")
        self.geometry("700x500")
        self.resizable(False, False)
        self.configure(bg=COLORS["bg"])

        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self._setup_styles()

        self.install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.opt_firewall = tk.BooleanVar(value=True)
        self.opt_startmenu = tk.BooleanVar(value=True)
        self.opt_desktop = tk.BooleanVar(value=True)
        self.opt_path = tk.BooleanVar(value=True)
        self.opt_service = tk.BooleanVar(value=False)
        self.opt_backend = tk.StringVar(value="gpu")
        self.opt_launch = tk.BooleanVar(value=False)
        self.license_accepted = tk.BooleanVar(value=False)

        self.pages: list[tk.Frame] = []
        self.current_page = 0

        self._build_welcome()
        self._build_license()
        self._build_options()
        self._build_progress()
        self._build_complete()

        self._show_page(0)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=COLORS["bg"], foreground=COLORS["text"],
                         fieldbackground=COLORS["bg_card"], borderwidth=0)
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["bg_card"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"],
                         font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"),
                         foreground=COLORS["text"])
        style.configure("Subtitle.TLabel", font=("Segoe UI", 11),
                         foreground=COLORS["text_dim"])
        style.configure("Version.TLabel", font=("Segoe UI", 9),
                         foreground=COLORS["text_dim"])
        style.configure("Heading.TLabel", font=("Segoe UI", 13, "bold"),
                         foreground=COLORS["text"])
        style.configure("Status.TLabel", font=("Segoe UI", 10),
                         foreground=COLORS["text_dim"], background=COLORS["bg"])
        style.configure("Success.TLabel", font=("Segoe UI", 16, "bold"),
                         foreground=COLORS["green"])

        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"),
                         background=COLORS["accent"], foreground="#ffffff",
                         padding=(24, 8))
        style.map("Accent.TButton",
                   background=[("active", COLORS["accent_hover"]),
                               ("disabled", COLORS["border"])],
                   foreground=[("disabled", COLORS["text_dim"])])

        style.configure("Secondary.TButton", font=("Segoe UI", 10),
                         background=COLORS["bg_card"], foreground=COLORS["text"],
                         padding=(16, 8))
        style.map("Secondary.TButton",
                   background=[("active", COLORS["border"])])

        style.configure("Link.TButton", font=("Segoe UI", 10, "underline"),
                         background=COLORS["bg"], foreground=COLORS["accent"],
                         padding=(0, 4), borderwidth=0)
        style.map("Link.TButton", background=[("active", COLORS["bg"])])

        style.configure("TCheckbutton", background=COLORS["bg"],
                         foreground=COLORS["text"], font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", COLORS["bg"])])

        style.configure("TRadiobutton", background=COLORS["bg"],
                         foreground=COLORS["text"], font=("Segoe UI", 10))
        style.map("TRadiobutton", background=[("active", COLORS["bg"])])

        style.configure("TEntry", fieldbackground=COLORS["bg_card"],
                         foreground=COLORS["text"], insertcolor=COLORS["text"],
                         padding=(8, 6))

        style.configure("Horizontal.TProgressbar", background=COLORS["accent"],
                         troughcolor=COLORS["bg_card"], borderwidth=0,
                         thickness=8)

    def _make_page(self) -> tk.Frame:
        frame = tk.Frame(self, bg=COLORS["bg"])
        self.pages.append(frame)
        return frame

    def _show_page(self, idx: int):
        for p in self.pages:
            p.place_forget()
        self.pages[idx].place(x=0, y=0, relwidth=1, relheight=1)
        self.current_page = idx

    def _next_page(self):
        self._show_page(self.current_page + 1)

    def _build_welcome(self):
        page = self._make_page()

        spacer = tk.Frame(page, bg=COLORS["bg"], height=60)
        spacer.pack()

        logo = tk.Label(page, text="◆  K W Y R E   A I", font=("Segoe UI", 28, "bold"),
                        fg=COLORS["accent"], bg=COLORS["bg"])
        logo.pack(pady=(0, 12))

        tagline = ttk.Label(page,
                            text="Air-Gapped AI Inference for Analysts\nWho Cannot Afford a Breach",
                            style="Subtitle.TLabel", justify="center")
        tagline.pack(pady=(0, 8))

        ver = ttk.Label(page, text=f"Version {VERSION}", style="Version.TLabel")
        ver.pack(pady=(0, 40))

        sep = tk.Frame(page, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=80, pady=(0, 20))

        desc = ttk.Label(page,
                         text="This wizard will guide you through the installation of Kwyre AI\n"
                              "on your Windows system.",
                         style="Subtitle.TLabel", justify="center")
        desc.pack(pady=(0, 30))

        btn_frame = tk.Frame(page, bg=COLORS["bg"])
        btn_frame.pack(side="bottom", pady=30)
        ttk.Button(btn_frame, text="Next →", style="Accent.TButton",
                   command=self._next_page).pack()

    def _build_license(self):
        page = self._make_page()

        ttk.Label(page, text="License Agreement", style="Heading.TLabel").pack(
            anchor="w", padx=40, pady=(30, 10))
        ttk.Label(page, text="Please read and accept the license agreement to continue.",
                  style="Subtitle.TLabel").pack(anchor="w", padx=40, pady=(0, 12))

        text_frame = tk.Frame(page, bg=COLORS["border"], padx=1, pady=1)
        text_frame.pack(fill="both", expand=True, padx=40, pady=(0, 12))

        text_widget = tk.Text(text_frame, wrap="word", font=("Consolas", 9),
                              bg=COLORS["bg_card"], fg=COLORS["text"],
                              insertbackground=COLORS["text"], selectbackground=COLORS["accent"],
                              relief="flat", padx=12, pady=10, spacing1=2)
        text_widget.insert("1.0", MIT_LICENSE)
        text_widget.configure(state="disabled")
        text_widget.pack(fill="both", expand=True)

        bottom = tk.Frame(page, bg=COLORS["bg"])
        bottom.pack(fill="x", padx=40, pady=(0, 30))

        self._license_next_btn = ttk.Button(bottom, text="Next →",
                                            style="Accent.TButton",
                                            command=self._next_page, state="disabled")
        self._license_next_btn.pack(side="right")

        def _on_accept():
            self._license_next_btn.configure(
                state="normal" if self.license_accepted.get() else "disabled"
            )

        ttk.Checkbutton(bottom, text="I accept the terms of the license agreement",
                         variable=self.license_accepted,
                         command=_on_accept).pack(side="left")

    def _build_options(self):
        page = self._make_page()

        ttk.Label(page, text="Installation Options", style="Heading.TLabel").pack(
            anchor="w", padx=40, pady=(30, 16))

        dir_frame = tk.Frame(page, bg=COLORS["bg"])
        dir_frame.pack(fill="x", padx=40, pady=(0, 16))
        ttk.Label(dir_frame, text="Install directory:").pack(anchor="w", pady=(0, 4))

        dir_input = tk.Frame(dir_frame, bg=COLORS["bg"])
        dir_input.pack(fill="x")
        entry = ttk.Entry(dir_input, textvariable=self.install_dir, font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(dir_input, text="Browse…", style="Secondary.TButton",
                   command=self._browse_dir).pack(side="right")

        opts_frame = tk.Frame(page, bg=COLORS["bg"])
        opts_frame.pack(fill="x", padx=40, pady=(0, 10))

        ttk.Checkbutton(opts_frame, text="Install Windows Firewall rules (Layer 2 security)",
                         variable=self.opt_firewall).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts_frame, text="Create Start Menu shortcut",
                         variable=self.opt_startmenu).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts_frame, text="Create Desktop shortcut",
                         variable=self.opt_desktop).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts_frame, text="Add to PATH",
                         variable=self.opt_path).pack(anchor="w", pady=2)
        ttk.Checkbutton(opts_frame, text="Install as Windows Service (auto-start)",
                         variable=self.opt_service).pack(anchor="w", pady=2)

        sep = tk.Frame(page, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=40, pady=10)

        backend_frame = tk.Frame(page, bg=COLORS["bg"])
        backend_frame.pack(fill="x", padx=40, pady=(0, 10))
        ttk.Label(backend_frame, text="Backend:").pack(anchor="w", pady=(0, 4))
        ttk.Radiobutton(backend_frame, text="GPU (NVIDIA CUDA) — recommended",
                         variable=self.opt_backend, value="gpu").pack(anchor="w", pady=2)
        ttk.Radiobutton(backend_frame, text="CPU (Kwyre Air — any hardware)",
                         variable=self.opt_backend, value="cpu").pack(anchor="w", pady=2)

        btn_frame = tk.Frame(page, bg=COLORS["bg"])
        btn_frame.pack(side="bottom", fill="x", padx=40, pady=30)
        ttk.Button(btn_frame, text="Install →", style="Accent.TButton",
                   command=self._start_install).pack(side="right")

    def _build_progress(self):
        page = self._make_page()

        ttk.Label(page, text="Installing Kwyre AI", style="Heading.TLabel").pack(
            anchor="w", padx=40, pady=(40, 20))

        self._progress_bar = ttk.Progressbar(page, mode="determinate", length=600,
                                              style="Horizontal.TProgressbar")
        self._progress_bar.pack(padx=40, pady=(0, 16))

        self._status_label = ttk.Label(page, text="Preparing installation...",
                                        style="Status.TLabel")
        self._status_label.pack(anchor="w", padx=40, pady=(0, 10))

        log_frame = tk.Frame(page, bg=COLORS["border"], padx=1, pady=1)
        log_frame.pack(fill="both", expand=True, padx=40, pady=(0, 30))

        self._log_text = tk.Text(log_frame, wrap="word", font=("Consolas", 9),
                                  bg=COLORS["bg_card"], fg=COLORS["text_dim"],
                                  relief="flat", padx=10, pady=8, state="disabled",
                                  height=10)
        self._log_text.pack(fill="both", expand=True)

    def _build_complete(self):
        page = self._make_page()

        spacer = tk.Frame(page, bg=COLORS["bg"], height=80)
        spacer.pack()

        ttk.Label(page, text="✓  Installation Complete", style="Success.TLabel").pack(
            pady=(0, 12))

        self._complete_path_label = ttk.Label(
            page, text="", style="Subtitle.TLabel", justify="center")
        self._complete_path_label.pack(pady=(0, 20))

        ttk.Checkbutton(page, text="Launch Kwyre AI now",
                         variable=self.opt_launch).pack(pady=(0, 12))

        ttk.Button(page, text="Open Chat UI in Browser", style="Secondary.TButton",
                   command=self._open_chat).pack(pady=(0, 20))

        ttk.Button(page, text="Finish", style="Accent.TButton",
                   command=self._finish).pack()

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.install_dir.get())
        if d:
            self.install_dir.set(d)

    def _log(self, msg: str):
        self._log_text.configure(state="normal")
        self._log_text.insert("end", msg + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _set_status(self, msg: str):
        self._status_label.configure(text=msg)

    def _set_progress(self, value: float):
        self._progress_bar["value"] = value

    def _start_install(self):
        self._next_page()
        thread = threading.Thread(target=self._run_install, daemon=True)
        thread.start()

    def _run_install(self):
        install_dir = self.install_dir.get()
        steps = [
            ("Checking system requirements...", self._step_check_requirements),
            ("Detecting GPU...", self._step_detect_gpu),
            ("Creating directories...", self._step_create_dirs),
            ("Copying files...", self._step_copy_files),
            ("Installing dependencies...", self._step_install_deps),
            ("Configuring firewall rules...", self._step_firewall),
            ("Creating shortcuts...", self._step_shortcuts),
            ("Generating security manifests...", self._step_manifests),
            ("Installation complete!", None),
        ]

        try:
            for i, (label, action) in enumerate(steps):
                progress = (i / (len(steps) - 1)) * 100
                self.after(0, self._set_progress, progress)
                self.after(0, self._set_status, label)
                self.after(0, self._log, f"  {label}")

                if action:
                    action(install_dir)

            self.after(0, self._set_progress, 100)
            self.after(0, self._on_install_complete)

        except Exception as exc:
            self.after(0, self._log, f"\n  ERROR: {exc}")
            self.after(0, self._set_status, f"Installation failed: {exc}")
            self.after(0, lambda: messagebox.showerror(
                "Installation Error",
                f"An error occurred during installation:\n\n{exc}"
            ))

    def _step_check_requirements(self, install_dir: str):
        import time
        time.sleep(0.3)
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        self.after(0, self._log, f"    Python {py_ver} detected")

    def _step_detect_gpu(self, install_dir: str):
        import time
        time.sleep(0.4)
        compiled = os.path.join(SCRIPT_ROOT, "build", "kwyre-dist", "kwyre-server.exe")
        self._use_compiled = os.path.exists(compiled)

        if self._use_compiled:
            self.after(0, self._log, "    Compiled binary found")
        else:
            self.after(0, self._log, "    Installing from Python source")

        if self.opt_backend.get() == "gpu":
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total",
                     "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    self.after(0, self._log, f"    GPU: {result.stdout.strip()}")
                else:
                    self.after(0, self._log, "    GPU detection skipped (nvidia-smi unavailable)")
            except Exception:
                self.after(0, self._log, "    GPU detection skipped")
        else:
            self.after(0, self._log, "    CPU backend selected — GPU not required")

    def _step_create_dirs(self, install_dir: str):
        import time
        time.sleep(0.2)
        os.makedirs(install_dir, exist_ok=True)
        model_dir = os.path.join(os.environ.get("USERPROFILE", ""), ".cache", "huggingface")
        os.makedirs(model_dir, exist_ok=True)
        self.after(0, self._log, f"    {install_dir}")

    def _step_copy_files(self, install_dir: str):
        import time

        if self._use_compiled:
            src = os.path.join(SCRIPT_ROOT, "build", "kwyre-dist", "kwyre-server.exe")
            dst = os.path.join(install_dir, "kwyre-server.exe")
            shutil.copy2(src, dst)
            self.after(0, self._log, "    Copied kwyre-server.exe")
        else:
            for d in ("server", "model", "security"):
                src_dir = os.path.join(SCRIPT_ROOT, d)
                if os.path.isdir(src_dir):
                    dst_dir = os.path.join(install_dir, d)
                    if os.path.exists(dst_dir):
                        shutil.rmtree(dst_dir)
                    shutil.copytree(src_dir, dst_dir)
                    self.after(0, self._log, f"    Copied {d}/")
                    time.sleep(0.15)

            req_src = os.path.join(SCRIPT_ROOT, "requirements-inference.txt")
            if os.path.isfile(req_src):
                shutil.copy2(req_src, install_dir)

        for d in ("chat", "docs"):
            src_dir = os.path.join(SCRIPT_ROOT, d)
            if os.path.isdir(src_dir):
                dst_dir = os.path.join(install_dir, d)
                if os.path.exists(dst_dir):
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)
                self.after(0, self._log, f"    Copied {d}/")
                time.sleep(0.15)

        env_example = os.path.join(SCRIPT_ROOT, ".env.example")
        if os.path.isfile(env_example):
            shutil.copy2(env_example, install_dir)
            env_file = os.path.join(install_dir, ".env")
            if not os.path.isfile(env_file):
                shutil.copy2(env_example, env_file)
                self.after(0, self._log, "    Created .env from .env.example")

        self._create_launch_script(install_dir)

    def _create_launch_script(self, install_dir: str):
        bat_path = os.path.join(install_dir, "start_kwyre.bat")

        if self._use_compiled:
            content = '@echo off\necho Starting Kwyre AI...\necho.\n"%~dp0kwyre-server.exe"\npause\n'
        else:
            if self.opt_backend.get() == "cpu":
                server_script = "server\\serve_cpu.py"
            else:
                server_script = "server\\serve_local_4bit.py"
            content = (
                '@echo off\n'
                'echo Starting Kwyre AI...\n'
                'echo.\n'
                f'"%~dp0venv\\Scripts\\python.exe" "%~dp0{server_script}"\n'
                'pause\n'
            )

        with open(bat_path, "w", encoding="ascii", errors="replace") as f:
            f.write(content)

        self.after(0, self._log, "    Created start_kwyre.bat")

    def _step_install_deps(self, install_dir: str):
        import time

        if self._use_compiled:
            self.after(0, self._log, "    Skipped (using compiled binary)")
            time.sleep(0.3)
            return

        venv_path = os.path.join(install_dir, "venv")
        venv_python = os.path.join(venv_path, "Scripts", "python.exe")

        if not os.path.isfile(venv_python):
            self.after(0, self._log, "    Creating virtual environment...")
            subprocess.run([sys.executable, "-m", "venv", venv_path],
                           check=True, capture_output=True)
            self.after(0, self._log, "    Virtual environment created")

        req_file = os.path.join(install_dir, "requirements-inference.txt")
        if os.path.isfile(req_file):
            self.after(0, self._log, "    Installing pip packages (this may take a while)...")
            subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip", "-q"],
                           capture_output=True)
            subprocess.run([venv_python, "-m", "pip", "install", "-r", req_file],
                           capture_output=True)
            self.after(0, self._log, "    Dependencies installed")

    def _step_firewall(self, install_dir: str):
        import time

        if not self.opt_firewall.get():
            self.after(0, self._log, "    Skipped (user opted out)")
            time.sleep(0.2)
            return

        if self._use_compiled:
            exe_path = os.path.join(install_dir, "kwyre-server.exe")
        else:
            exe_path = os.path.join(install_dir, "venv", "Scripts", "python.exe")

        try:
            subprocess.run(
                ["powershell", "-Command",
                 'Remove-NetFirewallRule -DisplayName "Kwyre-BlockOutbound" -ErrorAction SilentlyContinue'],
                capture_output=True, timeout=15
            )
            subprocess.run(
                ["powershell", "-Command",
                 'Remove-NetFirewallRule -DisplayName "Kwyre-AllowLocalhost" -ErrorAction SilentlyContinue'],
                capture_output=True, timeout=15
            )

            subprocess.run(
                ["powershell", "-Command",
                 f'New-NetFirewallRule -DisplayName "Kwyre-BlockOutbound" '
                 f'-Description "Block all outbound traffic from Kwyre process" '
                 f'-Direction Outbound -Action Block '
                 f'-Program "{exe_path}" -Profile Any'],
                capture_output=True, check=True, timeout=30
            )
            subprocess.run(
                ["powershell", "-Command",
                 f'New-NetFirewallRule -DisplayName "Kwyre-AllowLocalhost" '
                 f'-Description "Allow Kwyre to communicate on localhost only" '
                 f'-Direction Outbound -Action Allow '
                 f'-Program "{exe_path}" -RemoteAddress "127.0.0.1" -Profile Any'],
                capture_output=True, check=True, timeout=30
            )
            self.after(0, self._log, "    Firewall rules installed")
        except subprocess.CalledProcessError:
            self.after(0, self._log, "    Firewall rules require admin — skipped")
        except Exception as exc:
            self.after(0, self._log, f"    Firewall setup warning: {exc}")

    def _step_shortcuts(self, install_dir: str):
        import time
        bat_path = os.path.join(install_dir, "start_kwyre.bat")

        if self.opt_startmenu.get():
            try:
                self._create_shortcut(
                    os.path.join(
                        os.environ.get("APPDATA", ""),
                        "Microsoft", "Windows", "Start Menu", "Programs",
                        "Kwyre AI", "Kwyre AI.lnk"
                    ),
                    bat_path, install_dir
                )
                self.after(0, self._log, "    Start Menu shortcut created")
            except Exception as exc:
                self.after(0, self._log, f"    Start Menu shortcut warning: {exc}")

        if self.opt_desktop.get():
            try:
                desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
                self._create_shortcut(
                    os.path.join(desktop, "Kwyre AI.lnk"),
                    bat_path, install_dir
                )
                self.after(0, self._log, "    Desktop shortcut created")
            except Exception as exc:
                self.after(0, self._log, f"    Desktop shortcut warning: {exc}")

        if self.opt_path.get():
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Environment", 0,
                    winreg.KEY_READ | winreg.KEY_WRITE
                )
                current_path, _ = winreg.QueryValueEx(key, "Path")
                if install_dir.lower() not in current_path.lower():
                    new_path = current_path.rstrip(";") + ";" + install_dir
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                    import ctypes
                    HWND_BROADCAST = 0xFFFF
                    WM_SETTINGCHANGE = 0x001A
                    ctypes.windll.user32.SendMessageTimeoutW(
                        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0x0002, 5000, None
                    )
                    self.after(0, self._log, "    Added to user PATH")
                else:
                    self.after(0, self._log, "    Already in PATH")
                winreg.CloseKey(key)
            except Exception as exc:
                self.after(0, self._log, f"    PATH warning: {exc}")

        if self.opt_service.get():
            self.after(0, self._log, "    Windows Service installation: manual setup required")
            time.sleep(0.1)

    def _create_shortcut(self, lnk_path: str, target: str, working_dir: str):
        lnk_dir = os.path.dirname(lnk_path)
        os.makedirs(lnk_dir, exist_ok=True)

        ps_script = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{lnk_path}"); '
            f'$s.TargetPath = "{target}"; '
            f'$s.WorkingDirectory = "{working_dir}"; '
            f'$s.Description = "Start Kwyre AI Inference Server"; '
            f'$s.Save()'
        )
        subprocess.run(["powershell", "-Command", ps_script],
                       capture_output=True, check=True, timeout=15)

    def _step_manifests(self, install_dir: str):
        import time

        if self._use_compiled:
            self.after(0, self._log, "    Skipped (compiled binary)")
            time.sleep(0.2)
            return

        venv_python = os.path.join(install_dir, "venv", "Scripts", "python.exe")
        verify_script = os.path.join(install_dir, "security", "verify_deps.py")

        if os.path.isfile(venv_python) and os.path.isfile(verify_script):
            try:
                subprocess.run([venv_python, verify_script, "generate"],
                               capture_output=True, timeout=60)
                self.after(0, self._log, "    Dependency manifest generated")
            except Exception:
                self.after(0, self._log, "    Manifest generation skipped")
        else:
            self.after(0, self._log, "    Manifest generation skipped")
            time.sleep(0.2)

    def _on_install_complete(self):
        self._complete_path_label.configure(
            text=f"Kwyre AI has been installed to:\n{self.install_dir.get()}\n\n"
                 f"Server: http://127.0.0.1:8000\n"
                 f"Chat UI: http://127.0.0.1:8000/chat"
        )
        self._show_page(4)

    def _open_chat(self):
        import webbrowser
        webbrowser.open("http://127.0.0.1:8000/chat")

    def _finish(self):
        if self.opt_launch.get():
            bat = os.path.join(self.install_dir.get(), "start_kwyre.bat")
            if os.path.isfile(bat):
                subprocess.Popen(["cmd", "/c", bat], cwd=self.install_dir.get())
        self.destroy()


def main():
    if os.name != "nt":
        print("This installer is for Windows only.")
        sys.exit(1)

    app = KwyreInstaller()
    app.mainloop()


if __name__ == "__main__":
    main()
