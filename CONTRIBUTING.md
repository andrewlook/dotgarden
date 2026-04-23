# Contributing

## Setup

Install tools with [mise](https://mise.jdx.dev/):

```bash
mise install
git config core.hooksPath hooks
```

The second command tells git to use the repo's `hooks/` directory for git hooks
(instead of `.git/hooks/`). This way the pre-commit hook is version-controlled
and shared across machines — no need to run `pre-commit install`.

### Install the CLI for development

Install the package in editable mode so the `dotfile` command on your PATH
imports from your checkout:

```bash
uv tool install --editable .
```

`uv tool` creates an isolated venv and exposes `dotfile` at
`~/.local/bin/dotfile` (ensure `~/.local/bin` is on PATH). Verify:

```bash
command -v dotfile    # → ~/.local/bin/dotfile
uv tool list          # → dotgarden v0.3.0 (editable)
```

Source edits under `dotgarden/` are live through the editable install — no
reinstall needed after changing Python files. Only dependency changes (new
`pyyaml` version etc.) require `uv tool upgrade`.

To uninstall or refresh runtime deps:

```bash
uv tool uninstall dotgarden
uv tool upgrade dotgarden     # pulls new pyyaml etc; source edits are always live
```

### Exercising the CLI against a fake home

Working on `bootstrap` while your real `~` is in active use is stressful — a
bad test run can clobber your real symlinks. Set `DOTFILE_HOME` to redirect
every path the CLI touches (symlinks, `.dotfiles_env`, registered-file source
paths) to a throwaway directory, leaving your real home alone:

```bash
mkdir -p /tmp/dotfile-sandbox
DOTFILE_HOME=/tmp/dotfile-sandbox dotfile bootstrap --os macos --profile work
DOTFILE_HOME=/tmp/dotfile-sandbox dotfile status
```

The override applies to the whole invocation: `register`, `unregister`,
`status`, `bootstrap`, `env`, `doctor` — every subcommand resolves `~` against
whatever `DOTFILE_HOME` points at. No `--home` flag to thread through.
Combine with a git worktree for safe parallel development.

## Project Structure

```
dotgarden/          # Python source
  config.py         # Constants, environment config
  registry.py       # Registry CRUD operations
  paths.py          # Path validation, IDs, formatting
  symlinks.py       # Symlink operations, bootstrap logic
  cli/              # CLI argument parsing + command dispatch
  __init__.py       # Re-exports public API

tests/              # Unit tests (pytest)
  test_config.py, test_paths.py, test_registry.py,
  test_symlinks.py, test_cli.py, test_local.py, test_overlay.py
  integration/      # End-to-end bash harness, runs the installed CLI

examples/
  starter/          # Git submodule → andrewlook/dotgarden-template (the
                    # "clone this to start" repo). Bump with
                    # `dev/bump-starter-template`.

tests/fixtures/     # Reference layouts used by the integration harness
  full/, minimal/

completions/        # Shell completion definitions for `dotfile`
hooks/pre-commit    # Auto-stage formatter changes on commit
test-docker         # Build + run the integration harness in Docker
Dockerfile.test     # Integration test image (Ubuntu + uv + installed CLI)

pyproject.toml      # Package metadata + hatchling build config
.github/workflows/
  tests.yml         # CI: pytest matrix + Docker integration
  publish.yml       # PyPI trusted publishing on tag push
```

## Testing

See [TESTING.md](TESTING.md) for the full guide — unit tests, Docker integration tests, example layouts, and CI.

Quick start:

```bash
mise run test        # Run all unit tests
./test-docker        # Run integration tests in Docker (Linux)
```

## Tasks

All tasks are defined in `mise.toml` and run with `mise run`:

```bash
mise run test                              # Run all tests
mise run test:q                            # Run tests (quiet)
mise run test:file tests/test_registry.py  # Run a single test file
mise run test:docker                       # Run integration tests in Docker
mise run fmt                               # Format code (ruff)
mise run lint                              # Check formatting without changes
mise run clean                             # Wipe __pycache__, .pytest_cache, dist/
```

## Formatting & Linting

Pre-commit hooks handle formatting automatically on commit. The custom hook at
`hooks/pre-commit` auto-stages formatter changes so you don't have to manually
`git add` after a formatter rewrites a file. Lint errors still block the commit.

You can also run formatters manually:

```bash
mise run fmt         # Autoformat everything
mise run lint        # Check without changing files
```

### What's covered

| Files | Formatter | Linter | Config |
|-------|-----------|--------|--------|
| Python (`.py`) | [ruff](https://docs.astral.sh/ruff/) format + fix | ruff check | `ruff.toml` |
| TOML (`.toml`) | [pretty-format-toml](https://github.com/macisamuele/language-formatters-pre-commit-hooks) | — | — |

## Publishing

Tag-push triggers `.github/workflows/publish.yml`, which builds the sdist +
wheel and uploads to PyPI via trusted publishing (OIDC). No token needed in
CI.

```bash
# Bump version in pyproject.toml, commit, then:
git tag v0.3.1
git push origin v0.3.1
```

## The starter template submodule

`examples/starter/` is a git submodule pointing at
[`andrewlook/dotgarden-template`](https://github.com/andrewlook/dotgarden-template)
— the "clone this to start a dotfiles repo" template. Edits to the
starter happen upstream in `dotgarden-template`; this repo tracks a
pinned commit.

**Workflow for updating the starter:**

1. Edit in your clone of `andrewlook/dotgarden-template`. Open a PR
   there, merge it.
2. Back here, run `dev/bump-starter-template` to pull the new main
   commit and record a pointer-bump commit (`starter: bump to <sha>`).
3. Push that commit.

The script refuses to run if this repo has unrelated pending changes
(so the bump commit stays clean) or if the submodule is already at
the latest main.

**Cloning this repo**: `git clone --recurse-submodules …` or run
`git submodule update --init --recursive` after a regular clone, so
the starter content is available under `examples/starter/`.

## Design Principles

- **Library functions accept parameters** -- no mutable module globals. Config values are passed in, not read from global state.
- **Library functions raise exceptions** -- only the CLI layer (`dotgarden/cli.py`) calls `sys.exit()`.
- **Tests use temp directories** -- no monkey-patching module globals. `config.defaults()` is patched to return test paths.
