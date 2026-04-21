"""`dotfile list` — print all managed files (registered + bootstrap-managed)."""

import json

from dotgarden import config, symlinks
from dotgarden import registry as reg


def cmd_list(args):
    """List all managed files (registered + bootstrap-managed)."""
    cfg = config.defaults()
    dotfiles_dir = cfg['dotfiles_dir']
    home_dir = cfg['home_dir']
    registry_path = cfg['registry_path']

    registry = reg.load(registry_path)
    bootstrap_entries = symlinks.discover_bootstrap_managed(dotfiles_dir, home_dir, registry)

    all_entries = registry['registered_files'] + bootstrap_entries

    if not all_entries:
        print('No managed files.')
        return

    if args.json:
        print(json.dumps({'files': all_entries}, indent=2))
        return

    print(f'\n{"ID":<25} {"Target":<40} {"OS":<8} {"Profile":<10} {"Source"}')
    print('=' * 120)

    for entry in registry['registered_files']:
        os_display = entry.get('os') or 'all'
        profile_display = entry.get('profile') or 'all'
        target = f'$DOTFILES/{entry["repo_path"]}'
        print(
            f'{entry["id"]:<25} '
            f'{target:<40} '
            f'{os_display:<8} '
            f'{profile_display:<10} '
            f'{entry["source_path"]}'
        )

    for entry in bootstrap_entries:
        os_display = entry.get('os') or 'all'
        profile_display = entry.get('profile') or 'all'
        target = f'$DOTFILES/{entry["repo_path"]}'
        print(
            f'{entry["id"]:<25} '
            f'{target:<40} '
            f'{os_display:<8} '
            f'{profile_display:<10} '
            f'{entry["source_path"]}'
        )

    print()
