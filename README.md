<!--
  This README is published to PyPI as the project's long description. PyPI
  does not resolve relative markdown links against the source repo, so every
  internal doc link below uses an absolute https://github.com/... URL.
  Please keep them absolute — don't "tidy" them back to repo-relative paths.
-->

# dotgarden

Manage dotfiles by moving them into a git-tracked repo and pointing `$HOME` at
the repo-managed copies. `dotfile register` relocates a live config into the
repo and leaves a symlink behind; `dotfile bootstrap` replays those symlinks
(plus OS/profile variants) on any machine. Ships the `dotfile` CLI.

## Install

```bash
uv tool install dotgarden
# or
pipx install dotgarden
# or
pip install dotgarden
```

## Quick start

Start from the template repo rather than an empty directory:

```bash
git clone https://github.com/andrewlook/dotgarden-template.git ~/dotfiles
cd ~/dotfiles
dotfile bootstrap --os macos        # or --os linux
```

The template demonstrates the `.local` include pattern, OS/profile variants,
registered configs, and the directory conventions.

## Commands

| Command | Description |
|---------|-------------|
| `dotfile bootstrap` | Link files in `$HOME` to the repo-managed versions and generate `.local` include files |
| `dotfile status` | Check health of all managed symlinks |
| `dotfile register` | Move a config into the repo and symlink it back |
| `dotfile unregister` | Remove a config from management |
| `dotfile specialize` | Scaffold OS/profile variant files and wire their `.local` include |
| `dotfile list` | List all managed files |
| `dotfile doctor` | Find and remove stale symlinks |
| `dotfile env` | Show current OS, profile, and overlay |
| `dotfile ids` | Print entry IDs (for scripting) |

### `dotfile bootstrap`

```
dotfile bootstrap --os <macos|linux> [--profile <name>] [--overlay <dir>] [--dry-run]
```

Runs every symlink and `.local` generator from a clean slate. Safe to re-run.

- `--os` — required on first run; remembered in `~/.dotfiles_env` after.
- `--profile` — activates a profile's variant files and registry entries.
- `--overlay` — layers a second repo on top (see [GUIDE.md § Overlay](https://github.com/andrewlook/dotgarden/blob/main/GUIDE.md#9-overlay--carve-out-private-content)).
- `--dry-run` — print the plan without touching the filesystem.
- `--skip-registry` — only handle root + `.config/*` conventions, skip registered entries.
- `--skip-unsupported` — silently skip `.local` generation for tool types with no known include syntax.

Existing non-symlink files at a link location are preserved as `<path>.bak`
before being replaced.

### `dotfile register`

```
dotfile register <path> [--category <name>] [--os <os>] [--profile <name>] [--name <file>] [--overlay <dir>] [--force] [--dry-run] [-y]
```

Moves `<path>` into the repo (under `_<category>/` or the repo root) and
creates a symlink back. Errors if the destination already exists unless you
pass `--force`.

- `--category` — target subdirectory in the repo (auto-detected from the source path if omitted).
- `--os` / `--profile` — scope the entry so bootstrap only links it on matching machines.
- `--name` — rename the file inside the repo.
- `--overlay` — write into an overlay repo instead of the main one.
- `--force` — overwrite an existing registration or repo file.
- `-y` — skip the confirmation prompt.

### `dotfile specialize`

```
dotfile specialize <os|profile> <dotfile> [--dry-run]
```

Scaffolds variant files for an existing base dotfile and appends the `.local`
include line so bootstrap can generate the override file.

Works on root paths (`.gitconfig`) and nested paths under `.config/<tool>/`
(e.g. `.config/fish/config.fish`). Variant names come from the `os:` and
`profiles:` lists in `__registry__.yaml`. Idempotent — safe to re-run.

## Documentation

- [GUIDE.md](https://github.com/andrewlook/dotgarden/blob/main/GUIDE.md) —
  hands-on walkthrough: starting a repo, registering your first files,
  specializing for OS/profile, setting up an overlay
- [Starter template](https://github.com/andrewlook/dotgarden-template) — clone
  this to begin a new dotfiles repo
- Source and issue tracker:
  https://github.com/andrewlook/dotgarden

## Development

See [CONTRIBUTING.md](https://github.com/andrewlook/dotgarden/blob/main/CONTRIBUTING.md) for setup, testing (`mise run test`,
`./test-docker`), and the publish flow. The package layout, entry point
(`dotgarden.cli:main`), and test harness all live in this repo — edits
happen here directly.

The `examples/starter/` directory is mirrored to
[`andrewlook/dotgarden-template`](https://github.com/andrewlook/dotgarden-template)
as the clone-ready starting point documented in Quick start above.

## License

MIT — see [LICENSE](https://github.com/andrewlook/dotgarden/blob/main/LICENSE).
