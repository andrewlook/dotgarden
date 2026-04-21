"""Overlay resolution + validation, shared by bootstrap and register.

Two helpers form the public API of this module:

- `resolve_overlay(args, home_dir)` — walks the precedence cascade
  (--overlay flag > $DOTFILES_OVERLAY env > saved ~/.dotfiles_env). Returns
  `(overlay_dir, source_label)` or `(None, None)`. Exits with a clear error
  if a value resolves to a nonexistent path.

- `validate_overlay_scope(overlay_dir, main_dotfiles_dir, current_profile)` —
  given a resolved overlay dir, enforces the same-dir check, reads the
  overlay's declared `profile:` field, and validates against the caller's
  --profile. Returns the overlay's declared profile.

Both helpers sys.exit on failure so callers don't have to repeat the error
plumbing. Keep them lean — anything else goes into its own utils module.
"""

import os
import sys

from dotgarden import config, symlinks
from dotgarden import registry as reg
from dotgarden.cli.utils.logging import LOG


def resolve_overlay(args, home_dir):
    """Return (overlay_dir, source) from args/env/.dotfiles_env.

    Precedence: --overlay flag > $DOTFILES_OVERLAY env var > saved in
    ~/.dotfiles_env. `source` is a short label ("flag", "DOTFILES_OVERLAY env",
    ".dotfiles_env") so callers can log which path won. Returns (None, None)
    when nothing is configured. Performs an existence check when a value is
    found; on failure, logs an error and exits.
    """
    overlay_dir = getattr(args, 'overlay', None)
    source = 'flag' if overlay_dir else None
    if not overlay_dir:
        overlay_dir = os.environ.get('DOTFILES_OVERLAY')
        if overlay_dir:
            source = 'DOTFILES_OVERLAY env'
    if not overlay_dir:
        _, _, saved_overlay = config.read_dotfiles_env(home_dir)
        overlay_dir = saved_overlay
        if overlay_dir:
            source = '.dotfiles_env'
    if not overlay_dir:
        return None, None

    overlay_dir = os.path.expanduser(overlay_dir)
    if not os.path.isdir(overlay_dir):
        LOG.error(
            f'Overlay directory not found: {overlay_dir} (from {source}). '
            'Clone the overlay repo or unset it before rerunning.'
        )
        sys.exit(1)
    return overlay_dir, source


def validate_overlay_scope(overlay_dir, main_dotfiles_dir, current_profile):
    """Shared overlay validation for bootstrap and register.

    Given a resolved overlay_dir (from resolve_overlay), checks that:

    1. The overlay is not the same dir as the main dotfiles repo.
    2. The overlay's `__registry__.yaml` exists AND declares a `profile:`
       (via symlinks._read_overlay_profile — the authoritative reader).
    3. The caller's current profile (args.profile or equivalent) either
       matches the overlay's declared profile or is None.

    On any failure, logs an error and calls sys.exit(1). On success,
    returns the overlay's declared profile so the caller can use it as
    the final/inferred profile.
    """
    if os.path.abspath(overlay_dir) == os.path.abspath(main_dotfiles_dir):
        LOG.error(f'Overlay directory cannot be the main dotfiles dir: {overlay_dir}')
        sys.exit(1)

    try:
        overlay_profile = symlinks._read_overlay_profile(overlay_dir)
    except reg.RegistryError as e:
        LOG.error(str(e))
        sys.exit(1)

    if current_profile and current_profile != overlay_profile:
        LOG.error(
            f'--profile {current_profile!r} conflicts with overlay {overlay_dir} '
            f'which declares profile {overlay_profile!r}. '
            f"Drop --profile (the overlay's profile is used automatically) "
            f'or pass --profile {overlay_profile}.'
        )
        sys.exit(1)

    return overlay_profile
