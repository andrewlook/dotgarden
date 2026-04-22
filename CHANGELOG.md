# Changelog

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
- `prepare_symlink_target` handles directories (was crashing with `IsADirectoryError` on boxy)
- `check_status` uses `realpath` instead of `abspath` (fixes false `WRONG TARGET` through symlink chains)
- `.local` file writes are atomic (tempfile + `os.replace`)
- `remove()` removes first match only (prevents double-delete for shared repo_path entries)
- `~user` paths rejected with validation error (only `~/` supported)

### Tooling
- `bin/dotfile` uses `uv` inline script metadata (PEP 723) — no `pip install` needed
- `Dockerfile.test` and `bin/test-docker` for Linux CI testing
- `.md` files excluded from dotfile consideration by extension
- `boxy/init.sh` installs `uv` for bootstrap

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
