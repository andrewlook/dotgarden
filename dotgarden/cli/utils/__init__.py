"""Shared helpers for CLI subcommands.

Split into topic modules to avoid a kitchen-sink shared file:

- `utils.logging` — LOG singleton + named color helpers (color_label,
  color_hint, color_header) for the CLI's visual style.
- `utils.overlays` — overlay-dir resolution (precedence cascade) and
  profile validation, shared by `bootstrap` and `register`.

Import from the specific submodule, not from this __init__. Keeping this
empty makes the dependency direction explicit: e.g. register depends on
`utils.logging` and `utils.overlays`, not on "the shared grab-bag".
"""
