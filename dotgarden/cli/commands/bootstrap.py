"""`dotfile bootstrap` — symlink dotfiles and generate .local files."""

import sys
from collections import OrderedDict

from dotgarden import config, paths, symlinks
from dotgarden.cli.utils.logging import LOG
from dotgarden.cli.utils.overlays import resolve_overlay, validate_overlay_scope


def cmd_bootstrap(args):
    """Bootstrap dotfiles by creating symlinks."""
    cfg = config.defaults()
    dotfiles_dir = cfg['dotfiles_dir']
    home_dir = cfg['home_dir']

    if not args.os:
        LOG.error('--os is required (macos or linux)')
        sys.exit(1)

    overlay_dir, _source = resolve_overlay(args, home_dir)
    profile = args.profile
    if overlay_dir:
        overlay_profile = validate_overlay_scope(overlay_dir, dotfiles_dir, profile)
        # Infer profile from overlay when not explicitly passed.
        profile = overlay_profile

    # Prominent one-line header so the active config is unambiguous.
    if overlay_dir:
        sys.stderr.write(
            f'\033[2mBootstrap (os={args.os}, profile={profile} via overlay {overlay_dir})\033[0m\n'
        )
    else:
        profile_display = profile if profile else '(none)'
        sys.stderr.write(f'\033[2mBootstrap (os={args.os}, profile={profile_display})\033[0m\n')

    results = symlinks.bootstrap(
        dotfiles_dir=dotfiles_dir,
        home_dir=home_dir,
        os_type=args.os,
        profile=profile,
        skip_registry=args.skip_registry,
        dry_run=args.dry_run,
        overlay_dir=overlay_dir,
    )

    # Group by phase
    phases = OrderedDict()
    for action, link_path, target_path, phase in results:
        phases.setdefault(phase, []).append((action, link_path, target_path))

    for phase_name, entries in phases.items():
        print(f'  \033[2m{phase_name}\033[0m')
        for action, link_path, target_path in entries:
            display = paths.escape_spaces(paths.format_for_display(link_path, home_dir))
            if target_path:
                target_display = paths.escape_spaces(
                    paths.format_for_display(target_path, home_dir)
                )
                arrow = f'  ->  {target_display}'
            else:
                arrow = ''
            if action in ('created', 'would_create'):
                print(f'    \033[32m✓\033[0m \033[36m{display}\033[0m{arrow}')
            elif action in ('updated', 'would_update'):
                print(
                    f'    \033[33m✓\033[0m \033[36m{display}\033[0m{arrow}  \033[33m(updated)\033[0m'
                )
            elif action in ('repaired', 'would_repair'):
                print(
                    f'    \033[33m✓\033[0m \033[36m{display}\033[0m{arrow}  \033[33m(repaired)\033[0m'
                )
            elif action == 'ok':
                print(f'    \033[2m✓ {display}{arrow}\033[0m')
            elif action == 'missing':
                print(f'    \033[31m✗ {display}{arrow}  (missing)\033[0m')
        print()

    counts = {}
    for a, _, _, _ in results:
        counts[a] = counts.get(a, 0) + 1

    parts = []
    for action, label in [
        ('would_create', 'to create'),
        ('would_update', 'to update'),
        ('would_repair', 'to repair'),
        ('created', 'created'),
        ('updated', 'updated'),
        ('repaired', 'repaired'),
        ('ok', 'already ok'),
        ('missing', 'missing'),
    ]:
        n = counts.get(action, 0)
        if n:
            if action == 'missing':
                parts.append(f'\033[31m{n} {label}\033[0m')
            elif action in ('repaired', 'would_repair'):
                parts.append(f'\033[33m{n} {label}\033[0m')
            else:
                parts.append(f'{n} {label}')

    if args.dry_run:
        print(f'[DRY RUN] {", ".join(parts)}. No changes made.')
    else:
        print(f'✓ Bootstrap complete ({", ".join(parts)})')
