#!/usr/bin/env python3
"""
Kwyre AI — Build Pipeline
Compiles Python source into protected binaries via Nuitka,
then packages platform-specific installers.

Usage:
    python build.py compile          # Nuitka compile only
    python build.py installer        # Build installer for current platform
    python build.py all              # Compile + installer
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

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
DIST_BUILD_DIR = os.path.join(BUILD_DIR, "kwyre-dist")

COMPILE_MODULES = [
    "server/serve_local_4bit.py",
    "server/tools.py",
    "security/verify_deps.py",
    "security/license.py",
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
    """Compile Python modules into standalone binaries with Nuitka."""
    check_nuitka()

    os.makedirs(DIST_BUILD_DIR, exist_ok=True)

    entry = os.path.join(PROJECT_ROOT, "server", "serve_local_4bit.py")
    output_dir = os.path.join(BUILD_DIR, "nuitka-output")

    print("\n=== Nuitka Compilation ===")
    print(f"Entry point: {entry}")
    print(f"Output: {output_dir}")
    print()

    nuitka_cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        f"--output-dir={output_dir}",
        "--output-filename=kwyre-server" + (".exe" if PLAT == "windows" else ""),
        "--company-name=APOLLO CyberSentinel LLC",
        "--product-name=Kwyre AI",
        "--product-version=0.3.0",
        "--file-description=Kwyre AI Inference Server",
        "--copyright=Copyright 2025-2026 APOLLO CyberSentinel LLC",
        "--include-module=tools",
        "--include-module=spike_serve",
        "--include-module=verify_deps",
        "--include-module=license",
        "--include-package=peft",
        "--include-package=transformers",
        "--include-package=bitsandbytes",
        "--include-package=accelerate",
        "--include-package=safetensors",
        "--include-package=huggingface_hub",
        "--include-package=cryptography",
        "--nofollow-import-to=torch.testing",
        "--nofollow-import-to=torch.utils.tensorboard",
        "--nofollow-import-to=torch.distributed",
        "--nofollow-import-to=IPython",
        "--nofollow-import-to=matplotlib",
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=datasets",
        "--nofollow-import-to=trl",
        "--remove-output",
        "--assume-yes-for-downloads",
        "--python-flag=no_site",
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
    run(nuitka_cmd)

    binary_name = "kwyre-server" + (".exe" if PLAT == "windows" else "")
    compiled = os.path.join(output_dir, binary_name)

    if not os.path.exists(compiled):
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                if "kwyre" in f.lower():
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

    return compiled


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

    setup_iso = os.path.join(PROJECT_ROOT, "security", "setup_isolation.sh")
    if os.path.exists(setup_iso):
        dst = os.path.join(DIST_BUILD_DIR, "security", "setup_isolation.sh")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(setup_iso, dst)
        print("  [COPY] security/setup_isolation.sh")

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
#define MyAppVersion "0.3.0"
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
OutputBaseFilename=kwyre-ai-setup-0.3.0-win64
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
        print(f"\n[OK] Windows installer: {installer_out}\\kwyre-ai-setup-0.3.0-win64.exe")
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

    control = """Package: kwyre-ai
Version: 0.3.0
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
        deb_file = os.path.join(installer_out, "kwyre-ai_0.3.0_amd64.deb")
        run(["dpkg-deb", "--build", "--root-owner-group", deb_root, deb_file])
        print(f"\n[OK] Linux .deb: {deb_file}")
    else:
        print(f"\n[OK] .deb package staged at {deb_root}")
        print("     Build with: dpkg-deb --build --root-owner-group build/deb-package build/installers/kwyre-ai_0.3.0_amd64.deb")

    appimage_script = os.path.join(BUILD_DIR, "build-appimage.sh")
    with open(appimage_script, "w") as f:
        f.write("""#!/bin/bash
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
    ARCH=x86_64 "$APPIMAGETOOL" "$APP_DIR" "$SCRIPT_DIR/installers/Kwyre-AI-0.3.0-x86_64.AppImage"
    echo "[OK] AppImage: $SCRIPT_DIR/installers/Kwyre-AI-0.3.0-x86_64.AppImage"
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
    --version 0.3.0 \\
    --install-location / \\
    "$INSTALLERS/kwyre-ai-0.3.0-macos.pkg"

echo ""
echo "[OK] macOS installer: $INSTALLERS/kwyre-ai-0.3.0-macos.pkg"
echo ""
echo "To sign for distribution:"
echo "  productsign --sign 'Developer ID Installer: YOUR NAME' \\\\"
echo "    $INSTALLERS/kwyre-ai-0.3.0-macos.pkg \\\\"
echo "    $INSTALLERS/kwyre-ai-0.3.0-macos-signed.pkg"
echo ""
echo "To create a .dmg:"
echo "  hdiutil create -volname 'Kwyre AI' -srcfolder $PKG_ROOT/payload/opt/kwyre \\\\"
echo "    -ov $INSTALLERS/kwyre-ai-0.3.0-macos.dmg"
""")
    os.chmod(build_pkg_script, 0o755)

    print(f"  [OK] macOS .pkg structure: {mac_dir}")
    print(f"  [OK] launchd plist: {launchd_dir}/com.kwyre.ai.server.plist")
    print(f"  [OK] Build script: {build_pkg_script}")

    if PLAT == "darwin" and shutil.which("pkgbuild"):
        run(["bash", build_pkg_script])
    else:
        print("  [INFO] Run build-macos-pkg.sh on macOS to generate the .pkg")


def clean():
    """Remove all build artifacts."""
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
        print(f"[OK] Removed {BUILD_DIR}")
    else:
        print("[OK] Nothing to clean")


def main():
    parser = argparse.ArgumentParser(
        description="Kwyre AI — Build Pipeline (Nuitka + Platform Installers)"
    )
    parser.add_argument(
        "command",
        choices=["compile", "installer", "all", "clean", "package"],
        help="compile=Nuitka build, installer=platform pkg, all=both, package=stage dist, clean=remove artifacts"
    )
    parser.add_argument(
        "--platform",
        choices=["windows", "linux", "macos", "all"],
        default=None,
        help="Target platform for installer (default: auto-detect)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"  Kwyre AI Build Pipeline v0.3.0")
    print(f"  Platform: {PLAT} ({platform.machine()})")
    print(f"  Python:   {sys.version.split()[0]}")
    print("=" * 60)

    if args.command == "clean":
        clean()
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

    print("\n" + "=" * 60)
    print("  Build complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
