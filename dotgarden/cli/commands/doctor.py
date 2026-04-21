"""`dotfile doctor` — find and remove stale symlinks."""

import os

from dotgarden import config, paths, symlinks
from dotgarden import registry as reg


def cmd_doctor(args):
    """Find and remove stale symlinks in directories managed by dotfiles."""
    cfg = config.defaults()
    home_dir = cfg['home_dir']
    registry_path = cfg['registry_path']

    registry = reg.load(registry_path)
    dirs = symlinks.find_symlink_dirs(home_dir, registry)
    stale = symlinks.find_stale_symlinks(dirs)

    if not stale:
        print('No stale symlinks found.')
        return

    print(f'Found {len(stale)} stale symlink(s):\n')
    for link_path, dead_target in stale:
        display = paths.escape_spaces(paths.format_for_display(link_path, home_dir))
        print(
            f'  \033[31m✗\033[0m \033[36m{display}\033[0m  ->  {dead_target}  \033[31m(dead)\033[0m'
        )

    if args.dry_run:
        print('\n[DRY RUN] No changes made.')
        return

    print()
    response = input('Remove these stale symlinks? [y/N]: ').strip().lower()
    if response not in ['y', 'yes']:
        print('Cancelled.')
        return

    for link_path, _ in stale:
        os.unlink(link_path)
        display = paths.escape_spaces(paths.format_for_display(link_path, home_dir))
        print(f'  \033[32m✓\033[0m Removed \033[36m{display}\033[0m')

    print(f'\n✓ Removed {len(stale)} stale symlink(s).')
