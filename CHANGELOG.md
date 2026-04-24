# Changelog

## v0.3.0 (2026-04-23)

First release on PyPI. Install with `uv tool install dotgarden`, `pipx install dotgarden`, or `pip install dotgarden`.

### `.config/*` auto-discovery
- Top-level children of `<repo>/.config/` symlink 1:1 to `~/.config/<name>` without a registry entry
- Nested variant files (`config.macos.fish`, `config.work.fish`) ride along via the `.local` hub
- `__registry__.yaml` `ignore_dirs` opts specific subdirs out of auto-discovery

### `dotfile register` upgrades
- Convention-skip: when registering a `.config/*` path with no `--category` / `--os` / `--profile`, register uses the auto-discovery convention instead of adding a registry entry
- Replace prompt: when the repo already has a file at the destination, register asks `[y/N/diff]` instead of erroring out (`--force` still works for non-interactive callers)
- Overlay registration is profile-gated; cross-repo conflicts are detected before any file moves

### Safer `.local` generation
- Bootstrap fails loudly when a variant file's tool type has no known include syntax, instead of silently dropping it
- `--skip-unsupported` opts out; interactive runs prompt `[y/N]`

### Starter template extracted
- `examples/starter/` is now a git submodule tracking [`andrewlook/dotgarden-template`](https://github.com/andrewlook/dotgarden-template)
- CI initializes submodules on checkout so integration tests see the full starter fixture
- Template demonstrates all three placement mechanisms: root dotfiles, `.config/*` convention, and registry (with a `_cursor/` entry for the non-XDG target)

### Documentation
- New [GUIDE.md](https://github.com/andrewlook/dotgarden/blob/main/GUIDE.md) walkthrough: template setup, register, specialize, overlay, and the starter's `bootstrap.sh`
- README Quick Start rewritten with an ASCII tree of the template, a `__registry__.yaml` snippet for the Cursor entry, and a real `dotfile bootstrap` output example
- Command table slimmed to `dotfile <cmd>` rows with per-command explainer sections for `bootstrap`, `register`, and `specialize`
- README's internal doc links use absolute GitHub URLs so they render correctly on the PyPI project page
- Added `dotfile status` demo screenshot to the README intro

### Bug fixes
- Registry ID derivation strips the leading dot from each path segment (fixes IDs for nested paths like `.config/fish/config.fish`)

### Packaging
- Tag-push release flow wired up: pushing `v*` runs `.github/workflows/publish.yml`, which builds `sdist` + `wheel` and uploads via PyPI OIDC trusted publishing — no API tokens in CI
- Strict hatchling sdist allowlist — only package-relevant files (`dotgarden/`, `tests/`, `README.md`, `LICENSE`, `CHANGELOG.md`, `pyproject.toml`) ship to PyPI

## v0.2.0 (2026-04-15)

### Registry v3 compact format
- Entries are now terse `repo_path: source_path` YAML mappings (1 line each, down from 8)
- Eliminated redundant fields: `id` (derived from repo_path), `category` (YAML key), `registered_at` (git blame)
- OS/profile conditions moved to structural nesting (`cursor.macos: [...]`)
- `os` and `profiles` metadata stored in registry for tooling
- `load()` handles v1 (JSON), v2 (verbose YAML), and v3 (compact) transparently

### `.local` pattern for OS/profile overrides
- Base dotfiles include a single `.local` file; bootstrap auto-generates it
- Per-tool inclusion syntax: shell `source`, git `[include]`, tmux `source-file -q`
- `dotfile status` verifies `.local` health (exists, fresh, included by base)
- `dotfile specialize os|profile <dotfile>` scaffolds variant files

### Status output redesign
- Colored `[macos]` `[work]` tags with deterministic palette
- `.local` indicator inline under primary dotfiles
- Variant chains under OS/profile entries (`✓ ~/.macos.gitconfig <- .gitconfig.local <- .gitconfig`)
- `.config` categories grouped under parent header
- Section spacing: 2 blank lines between major sections, 1 between groups
- Registry categories tagged when all entries share an OS/profile condition

### File convention migration
- OS/profile files moved from `__macos__/`, `__linux__/`, `__work__/`, `__home__/` to repo root
- New naming: `.macos.zprofile`, `.work.gitconfig` (colocated with base files)
- Bootstrap filters variants by active OS/profile
- `.macos.ideavimrc` → `.ideavimrc` (not OS-specific)
- `__macos__/sketchybar` → `_sketchybar`
- All `__*__/` directories removed

### New commands
- `dotfile specialize os|profile <dotfile>` — scaffold OS/profile variants
- `dotfile ids` — print entry IDs (for completions/scripting)

### Shell completions
- Bash (`completions/dotfile.bash`), Fish (`_fish/completions/dotfile.fish`), Zsh (updated)
- All subcommands and flags covered
- `dotfile unregister` completes entry IDs via `dotfile ids`

### Bug fixes
- `prepare_symlink_target` handles directories (was crashing with `IsADirectoryError` on devbox)
- `check_status` uses `realpath` instead of `abspath` (fixes false `WRONG TARGET` through symlink chains)
- `.local` file writes are atomic (tempfile + `os.replace`)
- `remove()` removes first match only (prevents double-delete for shared repo_path entries)
- `~user` paths rejected with validation error (only `~/` supported)

### Tooling
- `bin/dotfile` uses `uv` inline script metadata (PEP 723) — no `pip install` needed
- `Dockerfile.test` and `bin/test-docker` for Linux CI testing
- `.md` files excluded from dotfile consideration by extension
- `devbox/init.sh` installs `uv` for bootstrap

### Documentation
- `docs/reference/local-pattern.md` — how the `.local` pattern works
- `docs/reference/fish-shell-setup.md` — rewritten for new conventions
- `TESTING.md` — unit tests, Docker integration tests, example layouts
- `examples/minimal/` and `examples/full/` — reference dotfile layouts
- `AGENTS.md` — default to feature branches, create PRs early

## v0.1.0 (2026-03-22)

### Initial release
- `dotfile register` — register any file/directory with auto-category detection
- `dotfile unregister` — restore files to original location
- `dotfile list` — show all managed files
- `dotfile status` — check symlink health
- `dotfile doctor` — find and remove stale symlinks
- `dotfile bootstrap` — create symlinks for all managed files
- `__registry__.json` (v1) → `__registry__.yaml` (v2) with category grouping
- Python library extracted to `lib/` with full test suite
- Pre-commit hooks for Python, shell, fish, TOML, JSON, JSONC
- GitHub Actions CI
