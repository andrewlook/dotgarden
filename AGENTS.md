# AGENTS.md

Guidance for AI agents working on the `dotgarden` Python package.

## What this repo is

`dotgarden` is an installable Python package that ships the `dotfile` CLI —
one binary for managing dotfile symlinks, registering configs, and bootstrapping
new machines. It's published to PyPI and installed by `uv tool install
dotgarden` (or `pipx`, `pip`). This repo is the canonical source; there are
no upstream subtrees feeding it.

Consumers pair it with a dotfiles repo of their own (see
[`andrewlook/dotgarden-template`](https://github.com/andrewlook/dotgarden-template)
for a starting point). The CLI reads `__registry__.yaml` from that repo and
creates symlinks into `$HOME`.

## Layout

| Path | Contents |
|------|----------|
| `dotgarden/` | Python source (imported as `dotgarden`). |
| `dotgarden/cli/` | Subcommand implementations (`commands/`) + arg parsing. |
| `dotgarden/config.py`, `paths.py`, `registry.py`, `symlinks.py` | Core logic. |
| `tests/` | Pytest unit tests (one file per top-level module). |
| `tests/integration/` | Bash harness run against the installed `dotfile` binary. |
| `examples/starter/` | Git submodule → `andrewlook/dotgarden-template`. Bump with `dev/bump-starter-template` after merging upstream changes there. |
| `tests/fixtures/` | Fixture repos used by the integration harness (`full/`, `minimal/`). |
| `completions/` | Bash and zsh completion scripts. |
| `Dockerfile.test` + `test-docker` | Integration image (Ubuntu + uv + install). |
| `.github/workflows/tests.yml` | CI: pytest matrix + Docker harness. |
| `.github/workflows/publish.yml` | PyPI trusted publishing on tag push. |

## Working here

- **Install for dev:** `uv tool install --editable .` — gives you a `dotfile`
  on PATH that imports your checkout. Source edits under `dotgarden/` are
  live; only dependency bumps need `uv tool upgrade`.
- **Run tests:** `mise run test` (pytest), `./test-docker` (integration harness
  in Linux Docker). See [TESTING.md](TESTING.md).
- **Format/lint:** `mise run fmt`, `mise run lint`. The pre-commit hook
  (install with `git config core.hooksPath hooks`) runs ruff automatically
  and auto-stages formatter output.
- **Safe sandboxing:** set `DOTFILE_HOME=/tmp/foo` to redirect every `~`
  resolution inside the CLI, so bootstrap experiments don't touch your real
  home. Every subcommand honors it.

## Coding conventions

- Python 3.10+ (`requires-python = ">=3.10"` in `pyproject.toml`). Type hints
  optional; match surrounding style.
- Indentation 4 spaces, single quotes (ruff format enforces).
- Tests use `unittest.TestCase` + pytest parametrize. One test file per
  source module; keep classes focused on a single public function.
- CLI subcommands live in `dotgarden/cli/commands/<name>.py` and expose a
  `cmd_<name>(args)` entry point wired up in `dotgarden/cli/main.py`.
- Registry format changes require bumping `KNOWN_REGISTRY_VERSIONS` in
  `dotgarden/registry.py` and adding a load path for the old version. The
  registry version is separate from the package version — format-only.

## Registry version rule

The `version:` field in `__registry__.yaml` tracks **registry format**, not
package version. Bump it only when a backwards-incompatible schema change
ships. `KNOWN_REGISTRY_VERSIONS` gates which values the loader accepts;
forgetting to update it will reject valid registries.

## Release flow

1. Bump `version = "..."` in `pyproject.toml`.
2. Update `CHANGELOG.md` with a new entry.
3. Commit + merge to `main`.
4. Tag `v<version>` and push. `.github/workflows/publish.yml` builds and
   publishes via PyPI trusted publishing (OIDC) — no token needed.

Never rename, re-home, or remove an existing public module without a
deprecation path — consumers import `dotgarden.config`, `dotgarden.registry`,
etc. directly from library code.

## Things to avoid

- Committing `.venv/`, `dist/`, `build/`, `*.egg-info/`, or `__pycache__/`.
  `mise run clean` wipes them.
- Introducing runtime dependencies beyond `pyyaml` without discussion —
  `dotfile` is meant to `uv tool install` cleanly on any fresh machine.
- Editing files under `examples/starter/` directly. It's a submodule —
  edit in `andrewlook/dotgarden-template` and bump the pointer with
  `dev/bump-starter-template`. Direct edits get lost on the next bump
  and never reach template consumers anyway.
- Auto-applying refactors across `dotgarden/cli/commands/` without running
  the full `mise run test` (subcommands share module-level state through
  `dotgarden.config` and re-exports).
