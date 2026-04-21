# Testing

## Quick Start

```bash
# Run all unit tests
mise run test

# Run a single test file
mise run test:file tests/test_local.py

# Run tests matching a keyword
uv run --with pytest --with pyyaml python -m pytest tests/ -k "variant" -v
```

## Unit Tests

Unit tests use temp directories to simulate `$HOME` and the dotfiles repo. No real symlinks or dotfiles are touched. They live under `tests/` so they ship inside the published sdist — anyone who installs the package can re-run them against their own environment.

```bash
# All tests (verbose)
mise run test

# Quiet mode
mise run test:q

# Single file
mise run test:file tests/test_registry.py
```

### Test files

| File | What it covers |
|------|---------------|
| `tests/test_config.py` | `NOT_DOTFILES`, `NOT_DOTFILES_DIRS`, `read_dotfiles_env`, `defaults()`, `_find_dotfiles_dir` branches |
| `tests/test_paths.py` | Path validation, ID generation, display formatting, category detection |
| `tests/test_registry.py` | YAML registry load/save roundtrip, category grouping, finders, add/remove |
| `tests/test_symlinks.py` | `list_dotfiles`, `prepare_symlink_target`, `create_symlink`, `check_status`, `bootstrap` phases, variant filtering, `.local` generation during bootstrap |
| `tests/test_local.py` | `is_os_specific`, `is_profile_specific`, `format_local_include`, `find_variant_files`, `generate_local_files`, `check_local_health` |
| `tests/test_cli.py` | `register`, `unregister`, `bootstrap`, `ids`, overlay precedence, `DOTFILE_HOME` override |
| `tests/test_overlay.py` | Overlay layering, collision, registry dedup, ignore_files |

### Writing tests

- Tests patch `config.defaults()` to use temp directories — see `CLITestCase` in `tests/test_cli.py`
- Use `tempfile.mkdtemp()` for isolation, clean up in `tearDown`
- Prefer parametrized tests for input/output variations
- Test both the happy path and edge cases (empty inputs, missing files, wrong OS/profile)

## Docker Integration Tests

Integration tests run the real `dotfile` CLI end-to-end against fixture repos
inside a clean Ubuntu container. No unit tests run in Docker — unit tests live
in `tests/` and run on the host.

### Prerequisites

- Docker Desktop (or Docker Engine on Linux)

### Running

```bash
# Build the image and run the bash harness
dev/test-docker

# Force a no-cache rebuild
dev/test-docker --rebuild

# Drop into an interactive shell in the test image
dev/test-docker --shell
```

### Harness layout

```
tests/integration/
├── lib.sh            — assertion helpers (assert_symlink_to, assert_file_contains, …)
├── run-all.sh        — driver: iterates every test_*.sh, reports pass/fail
├── test_bootstrap_variants.sh            — OS/profile filtering + .local generation
├── test_bootstrap_creates_bak.sh         — conflicting file is backed up to .bak
├── test_bootstrap_idempotent.sh          — second bootstrap run is a no-op
├── test_register_unregister.sh           — register → symlink → unregister → restore
├── test_status_healthy_and_broken.sh     — status output in both states
├── test_overlay.sh                       — overlay layering + collision + bad path
└── test_ignore_files.sh                  — registry ignore_files excludes from bootstrap
```

Each `test_*.sh` creates a fresh `$TEST_HOME` and `$TEST_REPO` under a temp dir,
copies a fixture from `examples/`, runs the `dotfile` command, and asserts
symlinks, file contents, and registry state. The harness installs the package
via `uv tool install .` so tests exercise the PyPI entry-point directly.

### Example layouts

The `examples/` directory contains reference dotfile layouts used as fixtures:

| Layout | Description |
|--------|-------------|
| `examples/minimal/` | Bare minimum: `.zprofile` and `.gitconfig`. No variants. |
| `examples/full/` | `.zprofile`, `.gitconfig`, `.tmux.conf` with macOS/Linux OS variants and work/home profile variants. |

### Adding a scenario

1. Drop a `tests/integration/test_<scenario>.sh` that sources `lib.sh`,
   calls `setup_workspace`, runs commands, and asserts.
2. `chmod +x` it.
3. Re-run `dev/test-docker`.

## CI

`.github/workflows/tests.yml` runs two jobs on every push / PR:

| Job | What it does |
|-----|--------------|
| `unit` | `pytest tests/` on Python 3.10 and 3.12. |
| `integration` | `docker build -f Dockerfile.test` + `docker run` → `tests/integration/run-all.sh`. |
