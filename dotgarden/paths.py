"""Path validation, ID generation, and display formatting utilities."""

import os
import re


def validate(path, dotfiles_dir, must_exist=True):
    """Validate and normalize a path.

    Expands ~ and environment variables, converts to absolute path.
    Raises FileNotFoundError if must_exist and path doesn't exist.
    Raises ValueError if path is inside the dotfiles repo.
    """
    # Reject ~user paths (only bare ~ for $HOME is supported)
    if path.startswith('~') and not path.startswith('~/') and path != '~':
        raise ValueError(f'Only ~/... paths are supported, not ~user paths: {path}')

    expanded = os.path.expanduser(os.path.expandvars(path))
    absolute = os.path.abspath(expanded)

    if must_exist and not os.path.exists(absolute):
        raise FileNotFoundError(f'Path does not exist: {absolute}')

    if absolute.startswith(dotfiles_dir):
        raise ValueError(f'Cannot register files inside dotfiles repo: {absolute}')

    return absolute


def generate_id(source_path, category):
    """Generate unique ID from source path and category.

    Example: ~/Library/Application Support/Code/User/settings.json + vscode
             -> vscode-settings
    """
    basename = os.path.splitext(os.path.basename(source_path))[0]
    slug = re.sub(r'[^\w\-]', '-', basename.lower())
    slug = re.sub(r'-+', '-', slug).strip('-')

    if category:
        return f'{category}-{slug}'
    return slug


def format_for_display(path, home_dir):
    """Format path for display, replacing home dir with ~."""
    if path.startswith(home_dir):
        return path.replace(home_dir, '~', 1)
    return path


def escape_spaces(path):
    """Escape spaces in path for shell copy-paste."""
    return path.replace(' ', '\\ ')


def auto_detect_category(source_path, home_dir):
    """Auto-detect category from source path.

    Returns category string or None for home directory files.
    """
    if 'Code/User' in source_path:
        return 'vscode'
    elif 'Cursor/User' in source_path:
        return 'cursor'
    elif '/.config/' in source_path:
        return source_path.split('/.config/')[-1].split('/')[0]
    elif os.path.dirname(source_path) == home_dir:
        return None
    else:
        return 'common'
