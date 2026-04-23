# Dotfiles

Personal configuration files, managed by
[dotgarden](https://github.com/andrewlook/dotgarden) (the `dotfile` CLI).

This is a reference layout showing all three of dotgarden's file-placement
mechanisms together — root dotfiles, the `.config/*` convention, and the
registry — so you can copy what fits and delete what doesn't.

## Install & bootstrap on a new machine

```bash
# 1. Install the CLI (via pipx, uv tool, or pip)
uv tool install dotgarden      # or: pipx install dotgarden

# 2. Clone this repo
git clone https://github.com/YOUR_USERNAME/dotfiles.git ~/dotfiles
cd ~/dotfiles

# 3. Preview, then bootstrap
dotfile bootstrap --os macos --dry-run
dotfile bootstrap --os macos

# Optional: activate a profile
dotfile bootstrap --os macos --profile work
```

## The three placement mechanisms

Dotgarden supports three ways to get a file from repo to `$HOME`. Each solves
a different problem. This example uses all three so you can compare.

### 1. Root dotfiles — convention, no registry

Files at the repo root symlink 1:1 to `$HOME`. No configuration needed.

```
<repo>/.gitconfig         → ~/.gitconfig
<repo>/.zprofile          → ~/.zprofile
<repo>/.tmux.conf         → ~/.tmux.conf
<repo>/.vimrc             → ~/.vimrc
<repo>/.aliases           → ~/.aliases
```

OS and profile variants live at the same level with a `.MOD.BASE` prefix:

```
<repo>/.macos.gitconfig   → ~/.macos.gitconfig    (when --os macos)
<repo>/.linux.gitconfig   → ~/.linux.gitconfig    (when --os linux)
<repo>/.work.zprofile     → ~/.work.zprofile      (when --profile work)
```

### 2. `.config/*` convention — also no registry

Top-level children of `<repo>/.config/` auto-symlink to `~/.config/<name>`.
The whole directory is a single symlink; everything inside rides along.

```
<repo>/.config/fish/      → ~/.config/fish        (directory symlink)
<repo>/.config/ghostty/   → ~/.config/ghostty     (directory symlink)
```

Inside a tool directory, nested variants use the `BASE.MOD.EXT` pattern
(different from root — here the leading dot belongs to `.config/`, not
to each file):

```
.config/fish/config.fish           # base
.config/fish/config.macos.fish     # sourced when --os macos
.config/fish/config.work.fish      # sourced when --profile work
```

### 3. Registry — for paths that are neither of the above

Some apps store config in inconvenient places:
`~/Library/Application Support/Cursor/User/settings.json`,
`~/.claude/skills/`, etc. The registry maps a clean repo path to the
actual target. This example registers Cursor:

```yaml
# __registry__.yaml
cursor:
  macos:
  - _cursor/settings.json: ~/Library/Application Support/Cursor/User/settings.json
  - _cursor/keybindings.json: ~/Library/Application Support/Cursor/User/keybindings.json
```

Use the registry when:

- The target path is outside `~/` and `~/.config/`
- The target is OS-conditional and the path differs per OS
- You want `dotfile unregister` to restore the original file cleanly

Don't use the registry for things the conventions already handle —
registering `~/.config/fish/` by hand is noise.

## The command sequence that produced this layout

If you started from an empty repo, here's (roughly) the sequence of
`dotfile` commands that would produce what you see:

```bash
# Start with an empty repo
git init ~/dotfiles && cd ~/dotfiles

# --- Create the registry metadata file ---
# Declare supported OS and profile names. Convention-discovered files and
# bootstrap both use these.
cat > __registry__.yaml <<EOF
version: '3.0'
os: [macos, linux]
profiles: [work, home]
EOF

# --- Add base root dotfiles ---
# Hand-place .gitconfig, .zprofile, .tmux.conf, .vimrc, .aliases. These are
# the "common" dotfiles — any file at the repo root that looks like a
# dotfile is auto-symlinked.

# --- Specialize for OS/profile ---
# Creates .macos.gitconfig / .linux.gitconfig and appends the [include]
# line at the bottom of .gitconfig pointing at .gitconfig.local.
dotfile specialize os .gitconfig
dotfile specialize os .zprofile
dotfile specialize os .tmux.conf

# .zprofile gets work/home profile variants too:
dotfile specialize profile .zprofile

# --- Add .config/<tool>/ content ---
# Just place files; no registration needed. Variants use BASE.MOD.EXT.
mkdir -p .config/fish .config/ghostty
# (write config.fish, config.macos.fish, .config/ghostty/config by hand)

# Wire fish's OS/profile .local hub in the same way:
dotfile specialize os .config/fish/config.fish

# --- Register Cursor's settings (non-XDG path) ---
# `register` moves the file from ~/Library/Application Support/... into
# _cursor/ and creates the symlink back. After this, edits to either
# location track together.
dotfile register ~/Library/Application\ Support/Cursor/User/settings.json \
    --category cursor --os macos
dotfile register ~/Library/Application\ Support/Cursor/User/keybindings.json \
    --category cursor --os macos

# --- Bootstrap everything ---
dotfile bootstrap --os macos
```

After bootstrap, your `$HOME` has:

- `~/.gitconfig` → repo's `.gitconfig`
- `~/.gitconfig.local` (auto-generated) → sources `.macos.gitconfig` when on macOS
- `~/.config/fish` → repo's `.config/fish/` (whole-dir symlink)
- `~/.config/fish/config.fish.local` (auto-generated) → sources the right variant
- `~/Library/Application Support/Cursor/User/settings.json` → repo's `_cursor/settings.json`

## Daily operations

| Command | Description |
|---------|-------------|
| `dotfile bootstrap --os <os> [--profile <p>] [--overlay <dir>]` | Create symlinks and regenerate `.local` files |
| `dotfile status` | Check health of all managed symlinks |
| `dotfile register <path>` | Register a new config file or directory (moves + symlinks) |
| `dotfile specialize os <path>` | Scaffold OS variants + wire `.local` include |
| `dotfile specialize profile <path>` | Same, for profiles |
| `dotfile unregister <id>` | Undo a `register` — restore the original file |
| `dotfile list` | List all managed files |
| `dotfile doctor` | Find and remove stale symlinks |
| `dotfile env` | Show current OS, profile, and overlay |

## Overlay directory (layered configs)

Keep work-specific configs in a private overlay repo while this one stays
public. The overlay declares its profile and contributes files that layer
on top of the main repo:

```bash
git clone git@github.com:YOU/dotfiles-work.git ~/dotfiles-work
dotfile bootstrap --os macos --profile work --overlay ~/dotfiles-work
```

Overlay root files are renamed with the overlay's profile prefix
(`.gitconfig` → `~/.work.gitconfig`). Overlay files under `.config/<tool>/`
must already carry the profile in the filename (e.g. `config.work.fish`).
See the dotgarden docs for the full rules.

## Structure

```
dotfiles/
├── .gitconfig                    # Common git config
├── .macos.gitconfig              # macOS overrides   (created by `specialize os`)
├── .linux.gitconfig              # Linux overrides
├── .zprofile                     # Common shell profile
├── .macos.zprofile
├── .linux.zprofile
├── .tmux.conf
├── .macos.tmux.conf
├── .linux.tmux.conf
├── .aliases
├── .vimrc
│
├── .config/
│   ├── fish/                     # CONVENTION: auto-discovered, no registry needed
│   │   ├── config.fish
│   │   └── config.macos.fish     # Nested variant (BASE.MOD.EXT)
│   └── ghostty/
│       └── config
│
├── _cursor/                      # REGISTRY: non-XDG target
│   ├── settings.json
│   └── keybindings.json
│
├── __registry__.yaml             # Declares os/profiles + registered categories
└── .gitignore                    # Ignores .local files
```
