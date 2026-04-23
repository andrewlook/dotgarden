# dotgarden guide

A walkthrough from zero to a working dotfiles repo. The README explains the
model; this file shows the actual commands in the order you'd run them.

Prerequisite: install the CLI once, globally.

```bash
uv tool install dotgarden      # or: pipx install dotgarden
dotfile --help
```

## 1. Start from the template

The [`dotgarden-template`](https://github.com/andrewlook/dotgarden-template)
repo is a working example of all three placement mechanisms (root dotfiles,
`.config/*` convention, registry). Clone it, point it at your own remote, and
push.

```bash
git clone https://github.com/andrewlook/dotgarden-template.git ~/dotfiles
cd ~/dotfiles

# Create your own empty repo on GitHub first (e.g. YOU/dotfiles), then:
git remote set-url origin git@github.com:YOU/dotfiles.git
git push -u origin main
```

From here on, `~/dotfiles` is your repo. Edit, add, and remove the template's
example files freely — they're just there to show you the patterns.

## 2. Register your first dotfile

`dotfile register <path>` **moves** the live file into `~/dotfiles` and leaves
a symlink behind. After this, editing either the system path or the repo path
edits the same file — they're the same inode.

```bash
dotfile register ~/.zshrc
```

**If the repo already has a file at the destination**, register stops with
`Destination already exists`. The starter ships example files for common
dotfiles (`.zprofile`, `.gitconfig`, `.tmux.conf`, …), so before registering
your system version:

- Delete the template copy from the repo (`rm ~/dotfiles/.zshrc`) if you want
  your system file to become the source of truth, then register.
- Or pass `--force` to overwrite the repo's version with your system version.

A safer first pass is to explore what the starter ships and delete any example
you don't want before registering your equivalents.

## 3. Register a `.config/` directory

Two options, pick one:

**Option A — use the convention** (preferred for tools that live under
`~/.config/<tool>/`). Copy the directory into `~/dotfiles/.config/` and
bootstrap — no registration needed. Every top-level child of
`~/dotfiles/.config/` auto-symlinks to `~/.config/<name>`.

```bash
cp -R ~/.config/ghostty ~/dotfiles/.config/ghostty
rm -rf ~/.config/ghostty     # bootstrap will recreate it as a symlink
```

**Option B — use `register`** if you want an entry in `__registry__.yaml`
(e.g. to scope the link with `--os` or `--profile`).

```bash
dotfile register ~/.config/ghostty --os macos
```

## 4. Register Cursor's settings (non-XDG path)

Some apps hide their config under `~/Library/Application Support/...`. The
registry is the right tool here — it maps an arbitrary target path to a clean
repo path and scopes it by OS.

```bash
dotfile register "~/Library/Application Support/Cursor/User/settings.json" \
    --category cursor --os macos
dotfile register "~/Library/Application Support/Cursor/User/keybindings.json" \
    --category cursor --os macos
```

The files land at `_cursor/settings.json` and `_cursor/keybindings.json` in
your repo, with entries added to `__registry__.yaml` under `cursor: macos:`.

## 5. Bootstrap

`bootstrap` is idempotent. Always dry-run it first to see the full plan.

```bash
dotfile bootstrap --os macos --dry-run
dotfile bootstrap --os macos
```

What bootstrap does for each managed file:

1. If `$HOME` doesn't have a file at the link location → create the symlink.
2. If `$HOME` has a symlink pointing at the right place → leave it.
3. If `$HOME` has a real file (or symlink to the wrong place) → **move it aside
   as `<path>.bak`**, then create the correct symlink.

The `.bak` behavior is the safety net for first-time bootstrap: any live
`~/.gitconfig` you haven't registered yet gets preserved at `~/.gitconfig.bak`
before it's replaced. If you wanted to keep that file, register it (or copy
its contents into the repo) before re-running bootstrap.

The `.dotfiles_env` file in `$HOME` remembers the OS, profile, and overlay
from the last bootstrap, so later runs can just be `dotfile bootstrap` with
no flags.

## 6. Check health with `status`

```bash
dotfile status
```

Shows every managed entry with one of:

- `✓` — symlink points where it should
- `✗ WRONG TARGET` — symlink points somewhere else (re-run bootstrap)
- `⚠ NOT SYMLINK` — there's a real file in the way (re-run bootstrap; it'll
  back up and replace)
- `⚠ UNLINKED` — repo has the file but `$HOME` doesn't (re-run bootstrap)
- `✗ MISSING` — registry entry points at a repo path that doesn't exist

## 7. Unregister and re-register

Undo a registration (restore the file to its original location, remove the
symlink, delete the repo copy):

```bash
dotfile unregister zshrc                 # by id
dotfile unregister ~/.zshrc              # by source path
dotfile unregister _cursor/settings.json # by repo path
```

To change how a file is registered (e.g. add `--os macos` scoping), unregister
and re-register:

```bash
dotfile unregister cursor-settings
dotfile register "~/Library/Application Support/Cursor/User/settings.json" \
    --category cursor --os macos
```

## 8. Specialize for OS or profile

`specialize` scaffolds the variant files and wires up the `.local` include
line so bootstrap can generate the right override file per machine.

```bash
# Create .macos.gitconfig, .linux.gitconfig (using os list from registry)
# and append `[include] path = ~/.gitconfig.local` to .gitconfig.
dotfile specialize os .gitconfig

# Create .work.gitconfig, .home.gitconfig for profiles.
dotfile specialize profile .gitconfig

# Always preview the resulting symlinks + .local files before committing.
dotfile bootstrap --dry-run
```

After bootstrap, `~/.gitconfig.local` is a generated file that sources
`.macos.gitconfig` + `.work.gitconfig` (or whichever match the active
machine). Put your machine-specific overrides in the variant files; never edit
the `.local` file by hand (bootstrap regenerates it).

Specialize also works on nested paths:

```bash
dotfile specialize os .config/fish/config.fish
```

## 9. Overlay — carve out private content

The overlay pattern is for the case where you want your main dotfiles repo to
be **public** (on GitHub, shared, reused across machines), but a subset of
configs need to stay **private** (work identity, employer-specific paths,
secrets-adjacent content).

The private content lives in a second repo that declares `profile: <name>`.
When you bootstrap with `--overlay <dir>`, files from the overlay are layered
on top of the main repo:

- Root-level overlay files use **bare** names (`.gitconfig`, not
  `.work.gitconfig`). Bootstrap renames them to `.<profile>.<basename>` at
  link time, so they flow through the main repo's `.local` hub.
- Overlay `__registry__.yaml` entries are implicitly scoped to the overlay's
  profile.
- Files under overlay `.config/<tool>/` must carry the profile in the filename
  explicitly (e.g. `config.work.fish`), because the nested dir is already a
  symlink into the main repo and can't be renamed at link time.

```bash
git clone git@github.com:YOU/dotfiles-work.git ~/dotfiles-work
dotfile bootstrap --os macos --profile work --overlay ~/dotfiles-work
```

After the first bootstrap, `--overlay` and `--profile` are remembered in
`~/.dotfiles_env`; later `dotfile bootstrap` calls don't need them.

A working example of an overlay repo:
[`andrewlook/dotfiles-work`](https://github.com/andrewlook/dotfiles-work) —
public-repo-unfriendly git identity + a `_boxy/` registered entry.

## 10. Bootstrap a new machine with `bootstrap.sh`

The starter template ships a `bootstrap.sh` meant to be piped from a URL on a
fresh machine. It installs `uv`, installs `dotgarden`, clones your dotfiles
repo into `~/dotfiles`, and runs `dotfile bootstrap` with whatever flags you
pass through.

```bash
# On a fresh machine, after editing the REPO_URL in bootstrap.sh:
curl -fsSL https://raw.githubusercontent.com/YOU/dotfiles/main/bootstrap.sh \
    | bash -s -- --os macos --profile work
```

Before using it, open `bootstrap.sh` and replace the `YOUR_USERNAME`
placeholder in `REPO_URL` with your GitHub handle (or set `DOTFILES_REPO` in
the environment to override at runtime).

## Reference

| Command | What it does |
|---------|--------------|
| `dotfile bootstrap` | Symlink everything; back up collisions as `.bak` |
| `dotfile status` | Health-check every managed symlink |
| `dotfile register` | Move a file into the repo, leave a symlink |
| `dotfile unregister` | Reverse a register |
| `dotfile specialize` | Scaffold OS/profile variants + wire `.local` include |
| `dotfile list` | Print all managed entries (convention + registry) |
| `dotfile doctor` | Find and remove stale symlinks |
| `dotfile env` | Print saved OS / profile / overlay |

For the flags each command takes, see [README.md](README.md#commands).
