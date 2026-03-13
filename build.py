#!/usr/bin/env python3
"""
Kwyre AI — Build Pipeline
Compiles Python source into protected binaries via Nuitka,
then packages platform-specific installers, signs releases,
and creates air-gap update packages.

Usage:
    python build.py compile          # Nuitka compile only
    python build.py package          # Stage data files
    python build.py installer        # Build installer for current platform
    python build.py sign             # Ed25519 sign all build artifacts
    python build.py update-package   # Create .kwyre-update for air-gap updates
    python build.py all              # Compile + package + installer + sign
    python build.py clean            # Remove build artifacts

Requirements:
    pip install nuitka ordered-set zstandard

Cross-platform builds require running on each target OS.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys

VERSION = "1.0.0"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
DIST_BUILD_DIR = os.path.join(BUILD_DIR, "kwyre-dist")

COMPILE_MODULES = [
    "server/serve_local_4bit.py",
    "server/serve_cpu.py",
    "server/serve_mlx.py",
    "server/security_core.py",
    "server/tools.py",
    "server/users.py",
    "server/audit.py",
    "server/analytics.py",
    "security/verify_deps.py",
    "security/license.py",
    "security/codesign.py",
    "security/updater.py",
    "model/spike_serve.py",
]

DATA_DIRS = [
    "chat",
    "docs",
    "security/kwyre_dep_manifest.json",
]

DATA_FILES = [
    "requirements-inference.txt",
    ".env.example",
    "LICENSE",
]

PLAT = platform.system().lower()


def run(cmd, **kwargs):
    print(f"  $ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str), **kwargs)
    if result.returncode != 0:
        print(f"  [FAIL] Exit code {result.returncode}")
        sys.exit(1)
    return result


def check_nuitka():
    try:
        import nuitka  # noqa: F401
        print("[OK] Nuitka found")
    except ImportError:
        print("[!] Nuitka not installed. Installing...")
        run([sys.executable, "-m", "pip", "install", "nuitka", "ordered-set", "zstandard"])


def compile_nuitka():
    """Compile proprietary Kwyre modules into native C with Nuitka.

    Strategy: Only YOUR code gets compiled into unreadable C binaries.
    Open-source ML libraries (torch, transformers, peft, etc.) are already
    compiled C/CUDA — no benefit to re-compiling and it would take hours.
    They get bundled as a frozen venv alongside the binary instead.

    What's protected (compiled to C, no .py source ships):
      - serve_local_4bit.py   (inference server, streaming, KV cache)
      - security_core.py      (6-layer security stack)
      - tools.py              (API tool router)
      - audit.py              (enterprise audit)
      - users.py              (multi-user RBAC)
      - spike_serve.py        (SpikeServe encoding — your IP)
      - verify_deps.py        (Layer 3 integrity)
      - license.py            (license validation + HW fingerprint)
      - codesign.py           (release signing)
      - updater.py            (air-gap updater)
      - serve_cpu.py          (CPU backend)
      - serve_mlx.py          (MLX backend)
    """
    check_nuitka()

    os.makedirs(DIST_BUILD_DIR, exist_ok=True)

    server_dir = os.path.join(PROJECT_ROOT, "server")
    output_dir = os.path.join(BUILD_DIR, "nuitka-output")
    entry = os.path.join(server_dir, "serve_local_4bit.py")

    CROSS_DIR_MODULES = {
        os.path.join(PROJECT_ROOT, "model", "spike_serve.py"): os.path.join(server_dir, "spike_serve.py"),
        os.path.join(PROJECT_ROOT, "security", "verify_deps.py"): os.path.join(server_dir, "verify_deps.py"),
        os.path.join(PROJECT_ROOT, "security", "license.py"): os.path.join(server_dir, "license.py"),
        os.path.join(PROJECT_ROOT, "security", "codesign.py"): os.path.join(server_dir, "codesign.py"),
        os.path.join(PROJECT_ROOT, "security", "updater.py"): os.path.join(server_dir, "updater.py"),
    }

    copied_files = []
    print("\n=== Nuitka Compilation ===")
    print(f"Entry point: {entry}")
    print(f"Output: {output_dir}")
    print(f"Strategy: Compile Kwyre IP to C, bundle ML libs as frozen venv")
    print()

    for src, dst in CROSS_DIR_MODULES.items():
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            copied_files.append(dst)
            print(f"  [STAGE] {os.path.basename(src)} -> server/")

    kwyre_modules = [
        "tools", "security_core", "audit", "users",
        "spike_serve", "verify_deps", "license", "codesign", "updater",
        "serve_cpu", "serve_mlx",
    ]

    nuitka_cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        f"--output-dir={output_dir}",
        "--output-filename=kwyre-server" + (".exe" if PLAT == "windows" else ""),
        "--company-name=APOLLO CyberSentinel LLC",
        "--product-name=Kwyre AI",
        f"--product-version={VERSION}",
        "--file-description=Kwyre AI Inference Server",
        "--copyright=Copyright 2025-2026 APOLLO CyberSentinel LLC",
    ]

    for mod in kwyre_modules:
        nuitka_cmd.append(f"--include-module={mod}")

    nuitka_cmd += [
        "--follow-import-to=tools",
        "--follow-import-to=security_core",
        "--follow-import-to=audit",
        "--follow-import-to=users",
        "--follow-import-to=spike_serve",
        "--follow-import-to=verify_deps",
        "--follow-import-to=license",
        "--follow-import-to=codesign",
        "--follow-import-to=updater",
        "--follow-import-to=serve_cpu",
        "--follow-import-to=serve_mlx",
        "--nofollow-import-to=torch",
        "--nofollow-import-to=transformers",
        "--nofollow-import-to=peft",
        "--nofollow-import-to=bitsandbytes",
        "--nofollow-import-to=accelerate",
        "--nofollow-import-to=safetensors",
        "--nofollow-import-to=huggingface_hub",
        "--nofollow-import-to=auto_gptq",
        "--nofollow-import-to=awq",
        "--nofollow-import-to=autoawq",
        "--nofollow-import-to=mlx",
        "--nofollow-import-to=mlx_lm",
        "--nofollow-import-to=llama_cpp",
        "--nofollow-import-to=IPython",
        "--nofollow-import-to=matplotlib",
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=datasets",
        "--nofollow-import-to=trl",
        "--assume-yes-for-downloads",
    ]

    if PLAT == "windows":
        icon = os.path.join(PROJECT_ROOT, "assets", "kwyre.ico")
        if os.path.exists(icon):
            nuitka_cmd.append(f"--windows-icon-from-ico={icon}")
        nuitka_cmd.append("--windows-console-mode=attach")
    elif PLAT == "darwin":
        icon = os.path.join(PROJECT_ROOT, "assets", "kwyre.icns")
        if os.path.exists(icon):
            nuitka_cmd.append(f"--macos-app-icon={icon}")

    nuitka_cmd.append(entry)

    try:
        run(nuitka_cmd)
    finally:
        for f in copied_files:
            if os.path.exists(f):
                os.remove(f)
                print(f"  [CLEAN] Removed staged {os.path.basename(f)}")

    binary_name = "kwyre-server" + (".exe" if PLAT == "windows" else "")
    binary_dir = os.path.join(output_dir, "serve_local_4bit.dist")
    compiled = os.path.join(binary_dir, binary_name)

    if not os.path.exists(compiled):
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                if "kwyre" in f.lower() and f.endswith((".exe", "")):
                    compiled = os.path.join(root, f)
                    break

    if os.path.exists(compiled):
        dest = os.path.join(DIST_BUILD_DIR, binary_name)
        shutil.copy2(compiled, dest)
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f"\n[OK] Compiled binary: {dest} ({size_mb:.1f} MB)")
    else:
        print(f"\n[WARN] Binary not found at expected path: {compiled}")
        print("       Check build/nuitka-output/ for the compiled file.")

    print("\n=== Bundling ML Runtime ===")
    _bundle_ml_runtime(skip_runtime=True)

    return compiled


def _bundle_ml_runtime(skip_runtime=False):
    """Create a frozen venv with ML dependencies alongside the binary.

    These are open-source compiled C/CUDA libraries — no IP to protect.
    They're shipped as-is so the compiled Kwyre binary can import them.
    """
    launcher = os.path.join(DIST_BUILD_DIR, "start-kwyre.bat" if PLAT == "windows" else "start-kwyre.sh")
    if PLAT == "windows":
        with open(launcher, "w") as f:
            f.write('@echo off\nset PYTHONPATH=%~dp0runtime\n"%~dp0kwyre-server.exe" %*\n')
    else:
        with open(launcher, "w") as f:
            f.write('#!/bin/bash\nexport PYTHONPATH="$(dirname "$0")/runtime"\n"$(dirname "$0")/kwyre-server" "$@"\n')
        os.chmod(launcher, 0o755)
    print(f"  [OK] Launcher: {launcher}")

    if skip_runtime:
        print("  [SKIP] Runtime bundling skipped (use 'python build.py bundle-runtime' to install)")
        return

    runtime_dir = os.path.join(DIST_BUILD_DIR, "runtime")
    os.makedirs(runtime_dir, exist_ok=True)

    reqs = os.path.join(PROJECT_ROOT, "requirements-inference.txt")
    if not os.path.exists(reqs):
        print("  [WARN] requirements-inference.txt not found, skipping runtime bundle")
        return

    print(f"  Installing ML runtime into {runtime_dir}")
    print("  (This downloads ~3 GB of PyTorch + ML libraries)")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--target", runtime_dir, "-r", reqs],
    )
    if result.returncode != 0:
        print("  [WARN] Runtime install failed — you can install manually:")
        print(f"         pip install --target {runtime_dir} -r {reqs}")
    else:
        print(f"  [OK] Runtime installed: {runtime_dir}")


def package_dist():
    """Copy data files and create the distribution layout."""
    print("\n=== Packaging Distribution ===")

    for d in DATA_DIRS:
        src = os.path.join(PROJECT_ROOT, d)
        dst = os.path.join(DIST_BUILD_DIR, d)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
            print(f"  [COPY] {d}/")
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  [COPY] {d}")

    for f in DATA_FILES:
        src = os.path.join(PROJECT_ROOT, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(DIST_BUILD_DIR, f))
            print(f"  [COPY] {f}")

    extra_security = [
        "security/setup_isolation.sh",
        "security/codesign.py",
        "security/updater.py",
        "security/license.py",
        "security/verify_deps.py",
    ]
    for rel in extra_security:
        src = os.path.join(PROJECT_ROOT, rel)
        if os.path.exists(src):
            dst = os.path.join(DIST_BUILD_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  [COPY] {rel}")

    installer_scripts = [
        "installer/install_windows.ps1",
        "installer/install_linux.sh",
        "installer/install_macos.sh",
        "installer/install_windows_gui.py",
    ]
    for rel in installer_scripts:
        src = os.path.join(PROJECT_ROOT, rel)
        if os.path.exists(src):
            dst = os.path.join(DIST_BUILD_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  [COPY] {rel}")

    import json
    version_json = {"version": VERSION, "build_platform": PLAT}
    vj_path = os.path.join(DIST_BUILD_DIR, "version.json")
    with open(vj_path, "w") as f:
        json.dump(version_json, f, indent=2)
    print(f"  [WRITE] version.json (v{VERSION})")

    print(f"\n[OK] Distribution staged at {DIST_BUILD_DIR}")


def build_windows_installer():
    """Generate Inno Setup script and build .exe installer."""
    print("\n=== Windows Installer (Inno Setup) ===")

    iss_path = os.path.join(BUILD_DIR, "kwyre-setup.iss")
    installer_out = os.path.join(BUILD_DIR, "installers")
    os.makedirs(installer_out, exist_ok=True)

    iss_content = f"""; Kwyre AI — Inno Setup Installer Script
; Auto-generated by build.py

#define MyAppName "Kwyre AI"
#define MyAppVersion "{VERSION}"
#define MyAppPublisher "APOLLO CyberSentinel LLC"
#define MyAppURL "https://kwyre.com"
#define MyAppExeName "kwyre-server.exe"

[Setup]
AppId={{{{A7F3B2C1-D4E5-6F78-9A0B-C1D2E3F4A5B6}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\KwyreAI
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
LicenseFile={os.path.join(DIST_BUILD_DIR, "LICENSE").replace("/", chr(92))}
OutputDir={installer_out.replace("/", chr(92))}
OutputBaseFilename=kwyre-ai-setup-{VERSION}-win64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={{src}}\\assets\\kwyre.ico
UninstallDisplayIcon={{app}}\\kwyre-server.exe
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "firewallrules"; Description: "Install Layer 2 network isolation (Windows Firewall rules)"; GroupDescription: "Security:"; Flags: checkedonce

[Files]
Source: "{DIST_BUILD_DIR.replace("/", chr(92))}\\kwyre-server.exe"; DestDir: "{{app}}"; Flags: ignoreversion
Source: "{DIST_BUILD_DIR.replace("/", chr(92))}\\chat\\*"; DestDir: "{{app}}\\chat"; Flags: ignoreversion recursesubdirs
Source: "{DIST_BUILD_DIR.replace("/", chr(92))}\\docs\\*"; DestDir: "{{app}}\\docs"; Flags: ignoreversion recursesubdirs
Source: "{DIST_BUILD_DIR.replace("/", chr(92))}\\security\\*"; DestDir: "{{app}}\\security"; Flags: ignoreversion recursesubdirs
Source: "{DIST_BUILD_DIR.replace("/", chr(92))}\\.env.example"; DestDir: "{{app}}"; Flags: ignoreversion
Source: "{DIST_BUILD_DIR.replace("/", chr(92))}\\requirements-inference.txt"; DestDir: "{{app}}"; Flags: ignoreversion

[Icons]
Name: "{{group}}\\Kwyre AI"; Filename: "{{app}}\\kwyre-server.exe"; Comment: "Start Kwyre AI Inference Server"
Name: "{{group}}\\Kwyre Chat UI"; Filename: "http://127.0.0.1:8000/chat"; IconFilename: "{{app}}\\kwyre-server.exe"
Name: "{{group}}\\Uninstall Kwyre AI"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\\Kwyre AI"; Filename: "{{app}}\\kwyre-server.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\kwyre-server.exe"; Description: "Launch Kwyre AI"; Flags: nowait postinstall skipifsilent

[Code]
procedure InstallFirewallRules;
var
  ResultCode: Integer;
begin
  Exec('powershell.exe',
    '-ExecutionPolicy Bypass -Command "' +
    'Remove-NetFirewallRule -DisplayName ''Kwyre-BlockOutbound'' -ErrorAction SilentlyContinue; ' +
    'Remove-NetFirewallRule -DisplayName ''Kwyre-AllowLocalhost'' -ErrorAction SilentlyContinue; ' +
    'New-NetFirewallRule -DisplayName ''Kwyre-BlockOutbound'' -Direction Outbound -Action Block -Program ''' +
    ExpandConstant('{{app}}') + '\\kwyre-server.exe'' -Profile Any | Out-Null; ' +
    'New-NetFirewallRule -DisplayName ''Kwyre-AllowLocalhost'' -Direction Outbound -Action Allow -Program ''' +
    ExpandConstant('{{app}}') + '\\kwyre-server.exe'' -RemoteAddress 127.0.0.1 -Profile Any | Out-Null"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure RemoveFirewallRules;
var
  ResultCode: Integer;
begin
  Exec('powershell.exe',
    '-ExecutionPolicy Bypass -Command "' +
    'Remove-NetFirewallRule -DisplayName ''Kwyre-BlockOutbound'' -ErrorAction SilentlyContinue; ' +
    'Remove-NetFirewallRule -DisplayName ''Kwyre-AllowLocalhost'' -ErrorAction SilentlyContinue"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsTaskSelected('firewallrules') then
      InstallFirewallRules;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFirewallRules;
end;
"""

    with open(iss_path, "w", encoding="utf-8") as f:
        f.write(iss_content)

    print(f"  [OK] Inno Setup script: {iss_path}")

    iscc = shutil.which("iscc") or shutil.which("ISCC")
    if not iscc:
        for candidate in [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ]:
            if os.path.exists(candidate):
                iscc = candidate
                break

    if iscc:
        print(f"  [OK] Inno Setup found: {iscc}")
        run([iscc, iss_path])
        print(f"\n[OK] Windows installer: {installer_out}\\kwyre-ai-setup-{VERSION}-win64.exe")
    else:
        print("  [INFO] Inno Setup (ISCC.exe) not found.")
        print("  [INFO] Install from: https://jrsoftware.org/isdl.php")
        print(f"  [INFO] Then run: iscc \"{iss_path}\"")
        print(f"  [INFO] Or install via: winget install JRSoftware.InnoSetup")


def build_linux_installer():
    """Generate .deb package and AppImage build script."""
    print("\n=== Linux Installer (.deb + AppImage) ===")

    deb_root = os.path.join(BUILD_DIR, "deb-package")
    install_prefix = os.path.join(deb_root, "opt", "kwyre")
    systemd_dir = os.path.join(deb_root, "etc", "systemd", "system")
    bin_dir = os.path.join(deb_root, "usr", "local", "bin")
    debian_dir = os.path.join(deb_root, "DEBIAN")

    for d in [install_prefix, systemd_dir, bin_dir, debian_dir]:
        os.makedirs(d, exist_ok=True)

    binary_name = "kwyre-server"
    src_binary = os.path.join(DIST_BUILD_DIR, binary_name)
    if os.path.exists(src_binary):
        shutil.copy2(src_binary, os.path.join(install_prefix, binary_name))
        os.chmod(os.path.join(install_prefix, binary_name), 0o755)

    for d in ["chat", "docs", "security"]:
        src = os.path.join(DIST_BUILD_DIR, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(install_prefix, d), dirs_exist_ok=True)

    for f in [".env.example"]:
        src = os.path.join(DIST_BUILD_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(install_prefix, f))

    control = f"""Package: kwyre-ai
Version: {VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: APOLLO CyberSentinel LLC <security@kwyre.ai>
Description: Kwyre AI — Air-Gapped Inference Server
 Locally-deployed AI inference with 6-layer security stack,
 cryptographic session wiping, and intrusion detection.
 Your queries never leave your machine.
Homepage: https://kwyre.com
Depends: libcudart12 | libcudart11.0
"""
    with open(os.path.join(debian_dir, "control"), "w") as f:
        f.write(control)

    postinst = """#!/bin/bash
set -e

# Create kwyre system user
if ! id kwyre &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin kwyre
fi

# Set ownership
chown -R kwyre:kwyre /opt/kwyre

# Install Layer 2 isolation if iptables available
if command -v iptables &>/dev/null; then
    KWYRE_UID=$(id -u kwyre)
    iptables -C OUTPUT -m owner --uid-owner "$KWYRE_UID" -j DROP 2>/dev/null || \
        iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" -j DROP
    iptables -C OUTPUT -m owner --uid-owner "$KWYRE_UID" -d 127.0.0.1 -j ACCEPT 2>/dev/null || \
        iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" -d 127.0.0.1 -j ACCEPT
    iptables -C OUTPUT -m owner --uid-owner "$KWYRE_UID" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
        iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" -m state --state ESTABLISHED,RELATED -j ACCEPT
    echo "[Layer 2] Network isolation rules installed for user kwyre"
fi

# Enable and start service
systemctl daemon-reload
systemctl enable kwyre.service
echo ""
echo "Kwyre AI installed to /opt/kwyre"
echo "Start with: sudo systemctl start kwyre"
echo "Chat UI:    http://127.0.0.1:8000/chat"
echo ""
"""
    with open(os.path.join(debian_dir, "postinst"), "w") as f:
        f.write(postinst)
    os.chmod(os.path.join(debian_dir, "postinst"), 0o755)

    prerm = """#!/bin/bash
set -e
systemctl stop kwyre.service 2>/dev/null || true
systemctl disable kwyre.service 2>/dev/null || true
"""
    with open(os.path.join(debian_dir, "prerm"), "w") as f:
        f.write(prerm)
    os.chmod(os.path.join(debian_dir, "prerm"), 0o755)

    postrm = """#!/bin/bash
set -e
if [ "$1" = "purge" ]; then
    # Remove iptables rules
    if command -v iptables &>/dev/null && id kwyre &>/dev/null; then
        KWYRE_UID=$(id -u kwyre)
        iptables -D OUTPUT -m owner --uid-owner "$KWYRE_UID" -j DROP 2>/dev/null || true
        iptables -D OUTPUT -m owner --uid-owner "$KWYRE_UID" -d 127.0.0.1 -j ACCEPT 2>/dev/null || true
        iptables -D OUTPUT -m owner --uid-owner "$KWYRE_UID" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
    fi
    userdel kwyre 2>/dev/null || true
    rm -rf /opt/kwyre
fi
systemctl daemon-reload
"""
    with open(os.path.join(debian_dir, "postrm"), "w") as f:
        f.write(postrm)
    os.chmod(os.path.join(debian_dir, "postrm"), 0o755)

    service_unit = """[Unit]
Description=Kwyre AI Inference Server
Documentation=https://kwyre.com
After=network.target

[Service]
Type=simple
User=kwyre
Group=kwyre
WorkingDirectory=/opt/kwyre
ExecStart=/opt/kwyre/kwyre-server
Restart=on-failure
RestartSec=5
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=KWYRE_BIND_HOST=127.0.0.1
LimitNOFILE=65536
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/kwyre
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"""
    with open(os.path.join(systemd_dir, "kwyre.service"), "w") as f:
        f.write(service_unit)

    launcher = """#!/bin/bash
exec /opt/kwyre/kwyre-server "$@"
"""
    launcher_path = os.path.join(bin_dir, "kwyre")
    with open(launcher_path, "w") as f:
        f.write(launcher)
    os.chmod(launcher_path, 0o755)

    if PLAT == "linux" and shutil.which("dpkg-deb"):
        installer_out = os.path.join(BUILD_DIR, "installers")
        os.makedirs(installer_out, exist_ok=True)
        deb_file = os.path.join(installer_out, f"kwyre-ai_{VERSION}_amd64.deb")
        run(["dpkg-deb", "--build", "--root-owner-group", deb_root, deb_file])
        print(f"\n[OK] Linux .deb: {deb_file}")
    else:
        print(f"\n[OK] .deb package staged at {deb_root}")
        print(f"     Build with: dpkg-deb --build --root-owner-group build/deb-package build/installers/kwyre-ai_{VERSION}_amd64.deb")

    appimage_script = os.path.join(BUILD_DIR, "build-appimage.sh")
    with open(appimage_script, "w") as f:
        f.write(f"""#!/bin/bash
set -euo pipefail

# Build Kwyre AI AppImage
# Requires: appimagetool (https://appimage.github.io/appimagetool/)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/Kwyre-AI.AppDir"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/usr/share/kwyre"

cp "$SCRIPT_DIR/kwyre-dist/kwyre-server" "$APP_DIR/usr/bin/"
cp -r "$SCRIPT_DIR/kwyre-dist/chat" "$APP_DIR/usr/share/kwyre/"
cp -r "$SCRIPT_DIR/kwyre-dist/docs" "$APP_DIR/usr/share/kwyre/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/kwyre-dist/security" "$APP_DIR/usr/share/kwyre/"
cp "$SCRIPT_DIR/kwyre-dist/.env.example" "$APP_DIR/usr/share/kwyre/" 2>/dev/null || true

cat > "$APP_DIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export KWYRE_DATA_DIR="$HERE/usr/share/kwyre"
exec "$HERE/usr/bin/kwyre-server" "$@"
APPRUN
chmod +x "$APP_DIR/AppRun"

cat > "$APP_DIR/kwyre-ai.desktop" << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=Kwyre AI
Comment=Air-Gapped AI Inference Server
Exec=kwyre-server
Icon=kwyre-ai
Categories=Utility;Science;
Terminal=true
DESKTOP

# Placeholder icon (replace with actual .png)
if [ -f "$SCRIPT_DIR/../assets/kwyre-256.png" ]; then
    cp "$SCRIPT_DIR/../assets/kwyre-256.png" "$APP_DIR/kwyre-ai.png"
else
    convert -size 256x256 xc:black -fill white -gravity center -pointsize 48 -annotate 0 "K" "$APP_DIR/kwyre-ai.png" 2>/dev/null || \
    echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > "$APP_DIR/kwyre-ai.png"
fi

APPIMAGETOOL=$(which appimagetool 2>/dev/null || echo "$HOME/appimagetool-x86_64.AppImage")
if [ -x "$APPIMAGETOOL" ]; then
    ARCH=x86_64 "$APPIMAGETOOL" "$APP_DIR" "$SCRIPT_DIR/installers/Kwyre-AI-{VERSION}-x86_64.AppImage"
    echo "[OK] AppImage: $SCRIPT_DIR/installers/Kwyre-AI-{VERSION}-x86_64.AppImage"
else
    echo "[INFO] appimagetool not found."
    echo "       Download: https://github.com/AppImage/appimagetool/releases"
    echo "       Then run: ARCH=x86_64 appimagetool $APP_DIR"
fi
""")
    os.chmod(appimage_script, 0o755)
    print(f"  [OK] AppImage build script: {appimage_script}")


def build_macos_installer():
    """Generate macOS .pkg installer build script and launchd plist."""
    print("\n=== macOS Installer (.pkg) ===")

    mac_dir = os.path.join(BUILD_DIR, "macos-pkg")
    payload_dir = os.path.join(mac_dir, "payload", "opt", "kwyre")
    scripts_dir = os.path.join(mac_dir, "scripts")
    launchd_dir = os.path.join(mac_dir, "payload", "Library", "LaunchDaemons")

    for d in [payload_dir, scripts_dir, launchd_dir]:
        os.makedirs(d, exist_ok=True)

    binary_name = "kwyre-server"
    src_binary = os.path.join(DIST_BUILD_DIR, binary_name)
    if os.path.exists(src_binary):
        shutil.copy2(src_binary, os.path.join(payload_dir, binary_name))

    for d in ["chat", "docs", "security"]:
        src = os.path.join(DIST_BUILD_DIR, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(payload_dir, d), dirs_exist_ok=True)

    for f in [".env.example"]:
        src = os.path.join(DIST_BUILD_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(payload_dir, f))

    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kwyre.ai.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/kwyre/kwyre-server</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/kwyre</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>UserName</key>
    <string>_kwyre</string>
    <key>GroupName</key>
    <string>_kwyre</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HF_HUB_OFFLINE</key>
        <string>1</string>
        <key>TRANSFORMERS_OFFLINE</key>
        <string>1</string>
        <key>KWYRE_BIND_HOST</key>
        <string>127.0.0.1</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/var/log/kwyre/server.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/kwyre/error.log</string>
</dict>
</plist>
"""
    with open(os.path.join(launchd_dir, "com.kwyre.ai.server.plist"), "w") as f:
        f.write(plist)

    postinstall = """#!/bin/bash
set -e

# Create kwyre service user
if ! dscl . -read /Users/_kwyre &>/dev/null 2>&1; then
    MAX_UID=$(dscl . -list /Users UniqueID | awk '{print $2}' | sort -n | tail -1)
    NEW_UID=$((MAX_UID + 1))
    dscl . -create /Users/_kwyre
    dscl . -create /Users/_kwyre UserShell /usr/bin/false
    dscl . -create /Users/_kwyre UniqueID "$NEW_UID"
    dscl . -create /Users/_kwyre PrimaryGroupID 20
    dscl . -create /Users/_kwyre RealName "Kwyre AI Service"
    echo "[OK] Created service user _kwyre (UID $NEW_UID)"
fi

# Set permissions
chown -R _kwyre:staff /opt/kwyre
chmod +x /opt/kwyre/kwyre-server

# Create log directory
mkdir -p /var/log/kwyre
chown _kwyre:staff /var/log/kwyre

# Symlink to PATH
ln -sf /opt/kwyre/kwyre-server /usr/local/bin/kwyre

# Load launchd service
launchctl load /Library/LaunchDaemons/com.kwyre.ai.server.plist 2>/dev/null || true

echo ""
echo "Kwyre AI installed to /opt/kwyre"
echo "Start:   sudo launchctl start com.kwyre.ai.server"
echo "Stop:    sudo launchctl stop com.kwyre.ai.server"
echo "Manual:  kwyre"
echo "Chat UI: http://127.0.0.1:8000/chat"
echo ""
"""
    with open(os.path.join(scripts_dir, "postinstall"), "w") as f:
        f.write(postinstall)
    os.chmod(os.path.join(scripts_dir, "postinstall"), 0o755)

    preinstall = """#!/bin/bash
# Stop existing service if running
launchctl stop com.kwyre.ai.server 2>/dev/null || true
launchctl unload /Library/LaunchDaemons/com.kwyre.ai.server.plist 2>/dev/null || true
"""
    with open(os.path.join(scripts_dir, "preinstall"), "w") as f:
        f.write(preinstall)
    os.chmod(os.path.join(scripts_dir, "preinstall"), 0o755)

    build_pkg_script = os.path.join(BUILD_DIR, "build-macos-pkg.sh")
    with open(build_pkg_script, "w") as f:
        f.write(f"""#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_ROOT="$SCRIPT_DIR/macos-pkg"
INSTALLERS="$SCRIPT_DIR/installers"
mkdir -p "$INSTALLERS"

echo "=== Building Kwyre AI macOS .pkg ==="

pkgbuild \\
    --root "$PKG_ROOT/payload" \\
    --scripts "$PKG_ROOT/scripts" \\
    --identifier com.kwyre.ai \\
    --version {VERSION} \\
    --install-location / \\
    "$INSTALLERS/kwyre-ai-{VERSION}-macos.pkg"

echo ""
echo "[OK] macOS installer: $INSTALLERS/kwyre-ai-{VERSION}-macos.pkg"
echo ""
echo "To sign for distribution:"
echo "  productsign --sign 'Developer ID Installer: YOUR NAME' \\\\"
echo "    $INSTALLERS/kwyre-ai-{VERSION}-macos.pkg \\\\"
echo "    $INSTALLERS/kwyre-ai-{VERSION}-macos-signed.pkg"
echo ""
echo "To create a .dmg:"
echo "  hdiutil create -volname 'Kwyre AI' -srcfolder $PKG_ROOT/payload/opt/kwyre \\\\"
echo "    -ov $INSTALLERS/kwyre-ai-{VERSION}-macos.dmg"
""")
    os.chmod(build_pkg_script, 0o755)

    print(f"  [OK] macOS .pkg structure: {mac_dir}")
    print(f"  [OK] launchd plist: {launchd_dir}/com.kwyre.ai.server.plist")
    print(f"  [OK] Build script: {build_pkg_script}")

    if PLAT == "darwin" and shutil.which("pkgbuild"):
        run(["bash", build_pkg_script])
    else:
        print("  [INFO] Run build-macos-pkg.sh on macOS to generate the .pkg")


def sign_release():
    """Sign the distribution directory with Ed25519."""
    print("\n=== Code Signing ===")
    if not os.path.isdir(DIST_BUILD_DIR):
        print(f"[FAIL] Distribution directory not found: {DIST_BUILD_DIR}")
        print("       Run 'python build.py package' first.")
        sys.exit(1)
    from security.codesign import sign_release as codesign_release
    codesign_release(DIST_BUILD_DIR, VERSION, PLAT)


def clean():
    """Remove all build artifacts."""
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
        print(f"[OK] Removed {BUILD_DIR}")
    else:
        print("[OK] Nothing to clean")


def verify_release():
    """Verify a signed distribution."""
    print("\n=== Verifying Release Signature ===")
    manifest = os.path.join(DIST_BUILD_DIR, "MANIFEST.sig.json")
    if not os.path.exists(manifest):
        print(f"[FAIL] No signed manifest at {manifest}")
        print("       Run 'python build.py sign' first.")
        sys.exit(1)
    from security.codesign import verify_release as codesign_verify
    ok = codesign_verify(manifest)
    if ok:
        print("[OK] Release signature and file hashes verified")
    else:
        print("[FAIL] Verification failed!")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Kwyre AI - Build Pipeline (Nuitka + Platform Installers)"
    )
    parser.add_argument(
        "command",
        choices=["compile", "package", "installer", "sign", "verify",
                 "update-package", "bundle-runtime", "all", "clean"],
        help=(
            "compile=Nuitka standalone binary, "
            "package=stage data files, "
            "installer=platform pkg (.exe/.deb/.pkg), "
            "sign=Ed25519 sign artifacts, "
            "verify=verify signed release, "
            "update-package=create .kwyre-update, "
            "bundle-runtime=install ML libs into dist, "
            "all=compile+package+installer+sign, "
            "clean=remove build/"
        ),
    )
    parser.add_argument(
        "--platform",
        choices=["windows", "linux", "macos", "all"],
        default=None,
        help="Target platform for installer (default: auto-detect)"
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"Kwyre AI Build Pipeline v{VERSION}",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"  Kwyre AI Build Pipeline v{VERSION}")
    print(f"  Platform: {PLAT} ({platform.machine()})")
    print(f"  Python:   {sys.version.split()[0]}")
    print("=" * 60)

    if args.command == "clean":
        clean()
        return

    if args.command == "verify":
        verify_release()
        return

    if args.command in ("compile", "all"):
        compile_nuitka()

    if args.command in ("package", "installer", "all"):
        package_dist()

    if args.command in ("installer", "all"):
        target = args.platform or PLAT
        if target in ("windows", "all"):
            build_windows_installer()
        if target in ("linux", "all"):
            build_linux_installer()
        if target in ("darwin", "macos", "all"):
            build_macos_installer()

    if args.command in ("sign", "all"):
        sign_release()

    if args.command == "bundle-runtime":
        _bundle_ml_runtime(skip_runtime=False)
        print("\n" + "=" * 60)
        print("  Build complete.")
        print("=" * 60)
        return

    if args.command == "update-package":
        if not os.path.isdir(DIST_BUILD_DIR):
            print("[!] Distribution not found. Run 'python build.py package' first.")
            sys.exit(1)
        from security.updater import KwyreUpdater
        updater = KwyreUpdater()
        installer_out = os.path.join(BUILD_DIR, "installers")
        os.makedirs(installer_out, exist_ok=True)
        output_path = os.path.join(installer_out, f"kwyre-{VERSION}.kwyre-update")
        out = updater.create_update_package(
            source_dir=DIST_BUILD_DIR,
            version=VERSION,
            changelog=f"Kwyre AI v{VERSION} release",
            output_path=output_path,
        )
        size_mb = os.path.getsize(out) / (1024 * 1024)
        print(f"\n[OK] Update package: {out} ({size_mb:.1f} MB)")

    print("\n" + "=" * 60)
    print("  Build complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
