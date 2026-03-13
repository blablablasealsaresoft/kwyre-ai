# Security

Security modules implementing layers 2-4 of the Kwyre security stack.

- `verify_deps.py` — Layer 3: SHA-256 dependency integrity verification
- `license.py` — Ed25519 offline license validation + hardware fingerprint binding
- `codesign.py` — Ed25519 release signing and verification
- `updater.py` — Air-gap safe update mechanism
- `setup_isolation.sh` — Layer 2: Process-level network isolation (iptables/WinFW/PF)
