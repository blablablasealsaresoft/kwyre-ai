# Tests

Test suites for the Kwyre server.

- `test_security.py` — Security layers 1-4, API auth, input validation, CSP (78 tests)
- `test_security_layer5_layer6.py` — Session storage, crypto wipe, intrusion watchdog (19 tests)
- `test_layer3_dependency_integrity.py` — Dependency manifest verification (10 tests)
- `test_integration.py` — HTTP endpoint integration tests (requires running server)
- `test_e2e.py` — Full end-to-end test suite (requires running server)

Run all: `python -m unittest discover -s tests -p "test_*.py" -v`
