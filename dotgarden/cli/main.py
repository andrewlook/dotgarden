"""Top-level argparse wiring + dispatch for the `dotfile` CLI.

`main()` is the entry point used by the pyproject `[project.scripts]` table
and by `dev/dotfile`. It:

1. Applies the DOTFILE_HOME override (if set) before anything reads HOME.
2. Builds the argparse tree with one subparser per command.
3. Dispatches args.command to the matching `cmd_<name>` function from
   `dotgarden.cli.commands`.

Keep this file declarative — command logic lives in `cli/commands/<name>.py`.
"""

import argparse
import os
import sys

from dotgarden.cli.commands import (
    cmd_bootstrap,
    cmd_doctor,
    cmd_env,
    cmd_ids,
    cmd_list,
    cmd_register,
    cmd_status,
    cmd_unregister,
)
from dotgarden.cli.utils.logging import LOG


def _apply_dotfile_home_override():
    """If DOTFILE_HOME is set, point HOME at that path for this process.

    Used for working on dotfiles from a worktree without touching your real
    home directory. Every dotfile subcommand reads HOME via config.defaults()
    or os.path.expanduser, so flipping HOME at entry-point time is enough to
    redirect all symlink creation, registry lookups, and .dotfiles_env I/O to
    the fake home.

    Lives in main.py (not in utils/) because it's a one-off entry-point hook
    — main() is the only caller.
    """
    override = os.environ.get('DOTFILE_HOME')
    if not override:
        return
    resolved = os.path.abspath(os.path.expanduser(override))
    if not os.path.isdir(resolved):
        LOG.error(f'DOTFILE_HOME directory does not exist: {resolved}')
        sys.exit(1)
    os.environ['HOME'] = resolved
    sys.stderr.write(f'\033[33m[dotfile: using DOTFILE_HOME={resolved}]\033[0m\n')


def _build_parser():
    parser = argparse.ArgumentParser(
        description='Manage dotfiles: register configs, bootstrap symlinks, and keep everything in sync.'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Register
    register_parser = subparsers.add_parser(
        'register',
        help='Register a file or directory',
        description='Move a file or directory into the dotfiles repo and create a symlink at the original location. '
        'The file is organized by category (auto-detected or specified with --category).',
    )
    register_parser.add_argument('path', help='Path to file or directory to register')
    register_parser.add_argument(
        '--category', help='Category for organization (auto-detected from path if omitted)'
    )
    register_parser.add_argument(
        '--os', choices=['macos', 'linux'], help='Only symlink on this OS during bootstrap'
    )
    register_parser.add_argument(
        '--profile', help='Only symlink for this profile during bootstrap (e.g. work, home)'
    )
    register_parser.add_argument(
        '--name', help='Custom filename in repo (default: keep original name)'
    )
    register_parser.add_argument(
        '--dry-run', action='store_true', help='Show what would happen without making changes'
    )
    register_parser.add_argument(
        '--force', action='store_true', help='Overwrite existing registration or destination'
    )
    register_parser.add_argument(
        '--overlay',
        help='Register into an overlay directory (with its own __registry__.yaml '
        'declaring profile:) instead of the main dotfiles repo. Falls back to '
        '$DOTFILES_OVERLAY / ~/.dotfiles_env saved overlay when this flag is omitted.',
    )
    register_parser.add_argument(
        '-y',
        '--yes',
        action='store_true',
        help='Skip the confirmation prompt (use with caution in scripts).',
    )

    # List
    list_parser = subparsers.add_parser(
        'list',
        help='List all managed files',
        description='Show all files managed by dotfiles, including both registered files '
        '(from __registry__.yaml) and bootstrap-managed files (from repo root and __os__/__profile__ dirs).',
    )
    list_parser.add_argument('--json', action='store_true', help='Output as JSON instead of table')

    # Status
    subparsers.add_parser(
        'status',
        help='Check symlink health',
        description='Verify that all managed symlinks are healthy. Shows which symlinks are '
        'working, broken, missing, or pointing to wrong targets. Run `dotfile bootstrap` to fix issues.',
    )

    # Unregister
    unreg_parser = subparsers.add_parser(
        'unregister',
        help='Unregister a file and restore it',
        description='Remove a file from dotfiles management. By default, restores the file to its '
        'original location (copies from repo, removes symlink, deletes repo copy). '
        'Use --no-restore to just remove the symlink and registry entry. '
        'Accepts an entry ID (e.g. zed-settings), source path (e.g. ~/.config/zed/settings.json), '
        'or repo path (e.g. _zed/settings.json).',
    )
    unreg_parser.add_argument(
        'id_or_path', help='Entry ID, source path, or repo path (e.g. _zed/settings.json)'
    )
    unreg_parser.add_argument(
        '--dry-run', action='store_true', help='Show what would happen without making changes'
    )
    unreg_parser.add_argument(
        '--no-restore',
        action='store_false',
        dest='restore',
        help='Do not copy the file back to its original location',
    )
    unreg_parser.add_argument(
        '--keep-symlink', action='store_true', help='Keep symlink in place (only with --no-restore)'
    )
    unreg_parser.add_argument(
        '--keep-file', action='store_true', help='Keep file in repo (only with --no-restore)'
    )

    # IDs
    subparsers.add_parser(
        'ids',
        help='Print registered entry IDs',
        description='Print one entry ID per line. Useful for shell completions and scripting.',
    )

    # Env
    subparsers.add_parser(
        'env',
        help='Print current OS, profile, and overlay',
        description='Print the current OS and profile from ~/.dotfiles_env.',
    )

    # Doctor
    doctor_parser = subparsers.add_parser(
        'doctor',
        help='Find and remove stale symlinks',
        description='Scan home directory and registered file locations for broken symlinks '
        'whose targets no longer exist. Shows what it found and prompts before removing.',
    )
    doctor_parser.add_argument(
        '--dry-run', action='store_true', help='Show stale symlinks without removing them'
    )

    # Bootstrap
    bootstrap_parser = subparsers.add_parser(
        'bootstrap',
        help='Create symlinks for all managed files',
        description='Create symlinks for all dotfiles: common (repo root), OS/profile variants '
        '(.macos.*, .work.*, etc.), and registered files. Generates .local override files '
        'for each tool type. Safe to run multiple times.',
    )
    bootstrap_parser.add_argument(
        '--os', choices=['macos', 'linux'], help='Operating system (required)'
    )
    bootstrap_parser.add_argument('--profile', help='Profile to activate (e.g. work, home)')
    bootstrap_parser.add_argument(
        '--skip-registry',
        action='store_true',
        help='Skip registered files, only bootstrap common/OS/profile',
    )
    bootstrap_parser.add_argument(
        '--overlay',
        help='Path to overlay directory with additional dotfiles (e.g. ~/dotfiles-work)',
    )
    bootstrap_parser.add_argument(
        '--dry-run', action='store_true', help='Show what would be done without making changes'
    )

    return parser


_COMMANDS = {
    'register': cmd_register,
    'list': cmd_list,
    'status': cmd_status,
    'unregister': cmd_unregister,
    'ids': cmd_ids,
    'env': cmd_env,
    'doctor': cmd_doctor,
    'bootstrap': cmd_bootstrap,
}


def main():
    _apply_dotfile_home_override()
    parser = _build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    _COMMANDS[args.command](args)
