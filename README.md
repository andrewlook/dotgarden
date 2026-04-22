# dotgarden

Manage dotfiles: register configs, bootstrap symlinks, and keep everything in
sync. Ships the `dotfile` CLI.

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
| `dotfile bootstrap --os <os> [--profile <p>] [--overlay <dir>]` | Create symlinks and generate `.local` files |
| `dotfile status` | Check health of all managed symlinks |
| `dotfile register <path>` | Move a config into the repo and symlink it back |
| `dotfile unregister <id>` | Remove a config from management |
| `dotfile list` | List all managed files |
| `dotfile doctor` | Find and remove stale symlinks |
| `dotfile env` | Show current OS, profile, and overlay |
| `dotfile ids` | Print entry IDs (for scripting) |

## Documentation

- [Starter template](https://github.com/andrewlook/dotgarden-template) — clone
  this to begin a new dotfiles repo
- Source and issue tracker:
  https://github.com/andrewlook/dotgarden

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, testing (`mise run test`,
`./test-docker`), and the publish flow. The package layout, entry point
(`dotgarden.cli:main`), and test harness all live in this repo — edits
happen here directly.

The `examples/starter/` directory is mirrored to
[`andrewlook/dotgarden-template`](https://github.com/andrewlook/dotgarden-template)
as the clone-ready starting point documented in Quick start above.

## License

MIT — see [LICENSE](./LICENSE).
