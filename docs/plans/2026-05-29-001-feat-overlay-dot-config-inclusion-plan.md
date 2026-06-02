---
title: "feat: overlay .config/<tool>/ inclusion (and the gaps around it)"
type: feat
status: proposed
date: 2026-05-29
author: andrewlook
---

# feat: overlay `.config/<tool>/` inclusion (and the gaps around it)

**Target repo:** `andrewlook/dotgarden`. Paths below are relative to the
dotgarden repo root unless noted.

## TL;DR — most of this already works

The original ask was: *"let me drop `dotfiles-work/.config/fish/config.work.fish`
in the overlay and have it get included into the main `~/.config/fish/` on
bootstrap."*

**This is already implemented.** An overlay can ship
`<overlay>/.config/<tool>/<base>.<profile>.<ext>` and bootstrap will wire it
into the corresponding `~/.config/<tool>/<base>.local` hub — sourced by
**absolute path**, with no symlink written through the main repo's
already-symlinked `.config/<tool>/` directory.

So the immediate use case (move the work fish config out of the public main
repo and into `dotfiles-work`) needs no new code — only a rename and a
`bootstrap` re-run. See [Usage today](#usage-today).

What this doc proposes is (1) documenting the existing behavior so it's
discoverable, and (2) closing two genuine gaps: bare `config.fish` rejection
with no escape hatch, and overlay-contributed tools that the main repo doesn't
already manage.

## How it works today

Three functions in `dotgarden/symlinks.py` already cover the nested-overlay
path:

1. **`_validate_overlay_dot_config()`** (`symlinks.py:646`) — walks
   `<overlay>/.config/<tool>/` and enforces the naming rule: every file must
   carry a modifier in its name (`config.work.fish`, `config.macos.fish`).
   A bare `config.fish` raises `RegistryError`, and a profile-tagged file
   whose profile ≠ the overlay's declared profile also raises.

2. **`_collect_overlay_dot_config_variants()`** (`symlinks.py:692`) — collects
   those files as variants of the base `.config/<tool>/<base>.<ext>`, keyed by
   the base path and stored as **absolute paths**. The docstring spells out
   why: the main repo's `~/.config/<tool>/` is itself a directory symlink into
   the main repo, so writing a file-level symlink "through" it would pollute
   the main repo. Sourcing by absolute path sidesteps that entirely.

3. **`_collect_variants()`** (`symlinks.py:731`) merges these into the variant
   map, and **`_generate_local_files()`** (`symlinks.py:830`) emits the
   `~/.config/<tool>/<base>.local` hub that sources them.

The base file (`~/.config/fish/config.fish`, symlinked from the main repo)
already sources `config.fish.local` at runtime, so the overlay's contribution
loads transparently on every shell start.

### Why bare `config.fish` is (intentionally) rejected

Root-level overlay dotfiles use **bare** names and get renamed to
`.<profile>.<basename>` at link time (`_link_root_dotfiles(..., rename_prefix=)`,
`symlinks.py:449`). Nested files can't use that trick: the parent
`~/.config/<tool>/` is a directory symlink, so there's no link-time rename
hook to disambiguate a bare `config.fish` from the main repo's base. Hence the
rule — **nested overlay files must self-tag** (`config.work.fish`), per the
error message at `symlinks.py:675`.

## Usage today

To move the work fish config from the public main repo into the private
overlay:

```bash
# 1. Move it into the overlay, keeping the profile tag in the name.
mkdir -p ~/tools/dotfiles-work/.config/fish
git -C ~/tools/dotfiles mv .config/fish/config.work.fish /tmp/cwf
mv /tmp/cwf ~/tools/dotfiles-work/.config/fish/config.work.fish

# 2. Re-bootstrap.
dotfile bootstrap --os macos --profile work --overlay ~/tools/dotfiles-work
```

After bootstrap, `~/.config/fish/config.fish.local` contains a line like:

```fish
test -e /Users/you/tools/dotfiles-work/.config/fish/config.work.fish; and source /Users/you/tools/dotfiles-work/.config/fish/config.work.fish
```

No symlink is created inside `~/.config/fish/`; the overlay file is sourced in
place.

## The actual gaps

### Gap 1 — overlay-contributed tools with no main-repo base

`_generate_local_files()` will happily `os.makedirs()` and write
`~/.config/<tool>/<base>.local` (`symlinks.py:869-870`) even for a tool the
main repo has never heard of. But the `.local` hub is inert unless **something
sources it**:

- The base file `~/.config/<tool>/<base>` doesn't exist (main repo has no such
  tool), so there's no symlink and nothing that does
  `source <base>.local`.
- Nothing else auto-sources arbitrary `~/.config/*/​*.local` files.

Result: an overlay shipping config for a tool that lives **only** in the
overlay (e.g. a work-only CLI) generates an orphaned `.local` file that's never
read. The fish case works only because the main repo already manages
`.config/fish/` and its base `config.fish` sources the hub.

**Possible fix:** when an overlay contributes the *only* variants for a tool
dir absent from the main repo, bootstrap should either (a) create the base
`~/.config/<tool>/<base>` (a real file that just sources the `.local` hub), or
(b) symlink the overlay's base file directly when the overlay also ships an
un-tagged base. Needs a decision on which.

### Gap 2 — whole-directory overlay contributions

`.config/*` convention discovery (`_link_dot_config_children`, `symlinks.py:430`)
maps each top-level child of `<repo>/.config/` to `~/.config/<name>` as a
**single directory symlink**. There's no merge: if both the main repo and the
overlay want to contribute files to the *same* `~/.config/<tool>/` dir, only
one can own the directory symlink. Today the main repo wins (overlay files ride
in as `.local`-sourced variants, per above). But an overlay that wants to own a
tool dir the main repo doesn't have falls into Gap 1.

**Possible fix:** allow an overlay to register a whole `.config/<tool>/` dir
via its `__registry__.yaml` (explicit entry → directory symlink to
`~/.config/<tool>/`), bypassing convention discovery. This is the lower-magic
option and may make Gap 1's "overlay-only tool" case moot.

### Gap 3 — discoverability

None of the above is documented. The behavior lives in function docstrings and
error messages. The README's overlay section mentions root-file renaming and
the `.local` hub but not nested `.config/<tool>/` variants.

**Fix:** document the naming rule (`config.<profile>.<ext>`, bare rejected) and
the absolute-path inclusion model in the overlay section of the README.

## Requirements trace

- **R1.** Document that overlays may ship `.config/<tool>/<base>.<profile>.<ext>`
  and that bare nested names are rejected. *(Gap 3)*
- **R2.** Define and implement behavior for an overlay tool dir with no
  main-repo base, so its config is actually sourced (not orphaned). *(Gap 1)*
- **R3.** Decide whether to support overlay-owned whole `.config/<tool>/`
  directories via registry entry, and implement if so. *(Gap 2)*
- **R4.** Cover the above with bootstrap tests: nested overlay variant included
  by absolute path; overlay-only tool sourced end-to-end; bare-name rejection.

## Open questions

1. For Gap 1, is creating a generated base file (option a) acceptable, or
   should overlay-only tools be required to go through an explicit registry
   entry (folding into Gap 2)?
2. Should bare `config.fish` in an overlay stay a hard error, or become a
   warning that auto-treats it as the overlay profile's variant (i.e. infer the
   tag)? Inference is friendlier but blurs the "self-tag" contract.
3. Do any real overlay tools need OS *and* profile tags simultaneously on a
   nested file (`config.macos.work.fish`)? `parse_nested_variant` parses a
   single modifier; multi-tag is out of scope unless there's demand.

## Prior art in this repo

- Root-level overlay rename: `_link_root_dotfiles(..., rename_prefix=)`,
  `symlinks.py:449`, `reject_variants=True` at `symlinks.py:482`.
- Nested overlay validation + collection: `symlinks.py:646`, `:692`, `:731`.
- `.local` hub generation: `_generate_local_files`, `symlinks.py:830`;
  include syntax per tool type in `dotgarden/config.py`.
- `.config/*` directory-symlink discovery: `_link_dot_config_children`,
  `symlinks.py:430`.
