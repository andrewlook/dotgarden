# Dotfiles

Personal configuration files, managed by [dotgarden](https://github.com/andrewlook/dotgarden).

## Quick Start

```bash
# Clone this repo
git clone https://github.com/YOUR_USERNAME/dotfiles.git ~/dotfiles
cd ~/dotfiles

# Install the dotfile CLI
pipx install dotgarden  # or: pip install dotgarden

# Preview what bootstrap will do
dotfile bootstrap --os macos --dry-run

# Run bootstrap
dotfile bootstrap --os macos

# Optional: activate a profile
dotfile bootstrap --os macos --profile work
```

## How It Works

### Common dotfiles

Files in the repo root (`.gitconfig`, `.zprofile`, `.tmux.conf`, etc.) are symlinked to `~/` on all systems.

### OS-specific overrides

Files named `.<os>.<tool>` are only symlinked on matching systems:

- `.macos.zprofile` — sourced on macOS only
- `.linux.gitconfig` — included on Linux only

### The `.local` pattern

Each base dotfile includes a `.local` counterpart. Bootstrap generates `.local` files with the correct includes for your OS and profile:

```
.gitconfig  →  includes .gitconfig.local  →  includes .macos.gitconfig
```

You never edit `.local` files — they're auto-generated and `.gitignore`'d.

### Registered configs

Configs outside `~/` (like `~/.config/ghostty/`) are tracked in `__registry__.yaml`:

```yaml
ghostty:
  macos:
    - .config/ghostty/config: ~/.config/ghostty/config
```

Register new configs with:

```bash
dotfile register ~/.config/some-tool/config
```

## Adding New Config

### Add a common dotfile

Just put it in the repo root. Bootstrap will symlink it to `~/`.

### Add OS-specific overrides

Drop an OS-prefixed file next to the base file and bootstrap will wire up the
`.local` include on the next run:

```bash
# Create macOS + Linux variants for .gitconfig
touch .macos.gitconfig .linux.gitconfig

# Add the include line at the bottom of .gitconfig (dotfile bootstrap
# also auto-generates ~/.gitconfig.local with the same effect):
printf '\n[include]\n    path = .gitconfig.local\n' >> .gitconfig

dotfile bootstrap --os macos
```

### Register an app config

```bash
dotfile register ~/.config/nvim
```

This moves the config into the repo and creates a symlink at the original location.

## Commands

| Command | Description |
|---------|-------------|
| `dotfile bootstrap --os <os> [--profile <p>] [--overlay <dir>]` | Create symlinks and generate `.local` files |
| `dotfile status` | Check health of all managed symlinks |
| `dotfile register <path>` | Register a new config file or directory |
| `dotfile unregister <id>` | Remove a config from management |
| `dotfile list` | List all managed files |
| `dotfile doctor` | Find and remove stale symlinks |
| `dotfile env` | Show current OS, profile, and overlay |
| `dotfile ids` | Print entry IDs (for scripting) |

### Overlay directory

Layer a second dotfiles repo on top of this one — useful for keeping
work-specific configs in a private repo while this one stays public:

```bash
git clone git@github.com:YOU/dotfiles-private.git ~/dotfiles-work
dotfile bootstrap --os macos --profile work --overlay ~/dotfiles-work
```

Overlay files win on collision. The overlay path is saved to
`~/.dotfiles_env` and reused on subsequent bootstrap runs.

## Structure

```
dotfiles/
├── .gitconfig                    # Common git config
├── .macos.gitconfig              # macOS overrides
├── .linux.gitconfig              # Linux overrides
├── .zprofile                     # Common shell profile
├── .macos.zprofile               # macOS shell setup
├── .linux.zprofile               # Linux shell setup
├── .tmux.conf                    # Common tmux config
├── .macos.tmux.conf              # macOS tmux overrides
├── .linux.tmux.conf              # Linux tmux overrides
├── .aliases                      # Shared shell aliases
├── .vimrc                        # Vim config
├── .config/ghostty/config        # Ghostty terminal config
├── _fish/                        # Fish shell configs
│   ├── config.fish
│   └── config.macos.fish
├── __registry__.yaml             # Registered file mappings
└── .gitignore                    # Ignores .local files
```

## Fish Shell

Fish configs live under `_fish/` and are registered in `__registry__.yaml`. The main `config.fish` sources OS/profile variants directly from the repo using `$DOTFILES` paths (no `.local` pattern needed for fish).

## Customization

1. **Fork this template** and clone to `~/dotfiles`
2. **Edit configs** — add your settings to the common files
3. **Add OS overrides** — `dotfile specialize os .gitconfig`
4. **Register app configs** — `dotfile register ~/.config/your-app`
5. **Bootstrap on new machines** — `dotfile bootstrap --os <os>`
