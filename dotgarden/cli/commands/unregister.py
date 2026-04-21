"""`dotfile unregister` — remove an entry + restore its original file."""

import os
import shutil
import sys

from dotgarden import config, paths
from dotgarden import registry as reg
from dotgarden.cli.utils.logging import LOG


def cmd_unregister(args):
    """Unregister a file and restore it to its original location."""
    cfg = config.defaults()
    dotfiles_dir = cfg['dotfiles_dir']
    home_dir = cfg['home_dir']
    registry_path = cfg['registry_path']

    registry = reg.load(registry_path)

    entry = reg.find_by_id(registry, args.id_or_path)
    if not entry:
        # Try as repo path (e.g. _fish/config.fish)
        entry = reg.find_by_repo_path(registry, args.id_or_path)
    if not entry:
        # Try as source path (e.g. ~/.config/fish/config.fish)
        try:
            source_path = paths.validate(args.id_or_path, dotfiles_dir, must_exist=False)
            entry = reg.find_by_source(registry, paths.format_for_display(source_path, home_dir))
        except ValueError:
            pass

    if not entry:
        LOG.error(f'No registered file found: {args.id_or_path}')
        LOG.error('Try: entry ID, source path, or repo path')
        sys.exit(1)

    entry_id = entry['id']
    source_path = os.path.expanduser(entry['source_path'])
    repo_path = os.path.join(dotfiles_dir, entry['repo_path'])
    source_display = paths.escape_spaces(entry['source_path'])
    repo_display = entry['repo_path']
    restore = args.restore

    # Check if other registry entries share the same repo file.
    # This happens when one repo file is symlinked to multiple locations
    # (e.g. a skill shared between ~/.claude/ and ~/.codex/).
    # If siblings exist, we must NOT delete the repo copy or we'd break them.
    siblings = [
        e for e in reg.find_all_by_repo_path(registry, entry['repo_path']) if e['id'] != entry_id
    ]
    has_siblings = len(siblings) > 0

    # If restore was requested but siblings exist, we can still copy the file
    # back to the source location — but we must keep the repo copy intact.
    keep_repo_file = has_siblings or args.keep_file

    # Preview
    print(f'\nUnregistering: {entry_id}')
    print(f'  Source: {source_display}')
    print(f'  Repo:   {repo_display}')
    if has_siblings:
        sibling_sources = ', '.join(e['source_path'] for e in siblings)
        print(f'  ⚠ Repo file is shared with: {sibling_sources}')
    print()
    print('This will:')
    print('  1. Remove from __registry__.yaml')
    if os.path.islink(source_path):
        if restore and os.path.exists(repo_path):
            print(f'  2. Remove symlink at {source_display}')
            print(f'  3. Copy {repo_display} back to {source_display}')
            if not keep_repo_file:
                print(f'  4. Delete {repo_display} from repo')
            elif has_siblings:
                print(f'  4. Keep {repo_display} in repo (still used by {sibling_sources})')
        else:
            print(f'  2. Remove symlink at {source_display}')
            if not keep_repo_file and os.path.exists(repo_path):
                print(f'  3. Delete {repo_display} from repo')
            elif has_siblings:
                print(f'  3. Keep {repo_display} in repo (still used by {sibling_sources})')
    print()

    if args.dry_run:
        print('[DRY RUN] No changes made.')
        return

    # Remove from registry
    reg.remove(registry, entry_id)
    reg.save(registry, registry_path, dotfiles_dir)
    print('✓ Removed from registry')

    # Restore: copy file back, remove symlink, optionally remove repo copy
    if restore and os.path.islink(source_path) and os.path.exists(repo_path):
        os.unlink(source_path)
        if os.path.isdir(repo_path):
            shutil.copytree(repo_path, source_path, symlinks=True)
            if not keep_repo_file:
                shutil.rmtree(repo_path)
        else:
            shutil.copy2(repo_path, source_path)
            if not keep_repo_file:
                os.remove(repo_path)
        print(f'✓ Restored {source_display}')
        if not keep_repo_file:
            print(f'✓ Removed {repo_display} from repo')
    else:
        # Remove symlink and optionally repo file
        if not args.keep_symlink and os.path.islink(source_path):
            os.unlink(source_path)
            print(f'✓ Removed symlink: {source_display}')

        if not keep_repo_file and os.path.exists(repo_path):
            if os.path.isdir(repo_path):
                shutil.rmtree(repo_path)
            else:
                os.remove(repo_path)
            print(f'✓ Removed from repo: {repo_display}')

    print(f'\n✓ Successfully unregistered: {entry_id}')
