"""Shared constants and environment configuration for dotfiles management."""

import os

REGISTRY_FILENAME = '__registry__.yaml'

# Default OS and profile values; overridable via registry metadata.
DEFAULT_OS_NAMES = ['macos', 'linux']
DEFAULT_PROFILES = ['work', 'home']

# File extensions in the repo root that are never dotfiles.
NOT_DOTFILES_EXTENSIONS = ['.md']

# Package defaults — files that are never dotfiles in any repo.
# Repos extend this list via registry metadata: ignore_files: [...]
NOT_DOTFILES = [
    '.editorconfig',
    '.git',
    '.gitkeep',
    '.gitignore',
    '.pre-commit-config.yaml',
    REGISTRY_FILENAME,
]

# Package defaults — directories that are never dotfiles.
# Repos extend via registry metadata: ignore_dirs: [...]
NOT_DOTFILES_DIRS = [
    'bin',
    'tests',
    '.git',
    '.github',
    '.pytest_cache',
]


def is_os_specific(filename, os_names=None):
    """Check if filename starts with .<os>. prefix.

    Returns the OS name if matched, None otherwise.
    """
    if os_names is None:
        os_names = DEFAULT_OS_NAMES
    for os_name in os_names:
        if filename.startswith(f'.{os_name}.'):
            return os_name
    return None


def is_profile_specific(filename, profiles=None):
    """Check if filename starts with .<profile>. prefix.

    Returns the profile name if matched, None otherwise.
    """
    if profiles is None:
        profiles = DEFAULT_PROFILES
    for profile in profiles:
        if filename.startswith(f'.{profile}.'):
            return profile
    return None


# Tool-type detection for .local file generation.
# Maps dotfile basenames to the syntax family used for inclusion.
LOCAL_TOOL_TYPES = {
    '.zprofile': 'shell',
    '.zshrc': 'shell',
    '.bashrc': 'shell',
    '.bash_profile': 'shell',
    '.profile': 'shell',
    '.aliases': 'shell',
    '.functions': 'shell',
    '.gitconfig': 'git',
    '.tmux.conf': 'tmux',
}


def format_local_include(tool_type, variant_filename):
    """Return the inclusion line for a variant file, per tool type."""
    home_path = f'~/{variant_filename}'
    if tool_type == 'shell':
        return f'[[ -f {home_path} ]] && . {home_path}'
    elif tool_type == 'git':
        return f'[include]\n    path = {variant_filename}'
    elif tool_type == 'tmux':
        return f'source-file -q {home_path}'
    else:
        return f'# include {variant_filename}'


def _unquote(value):
    """Strip surrounding single or double quotes from a shell-export value."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def read_dotfiles_env(home_dir):
    """Read OS, profile, and overlay from ~/.dotfiles_env.

    Returns (os_type, profile, overlay_dir) tuple. overlay_dir may be None.
    """
    env_path = os.path.join(home_dir, '.dotfiles_env')
    os_type = None
    profile = None
    overlay = None
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('export DOTFILES_OS='):
                    os_type = _unquote(line.split('=', 1)[1])
                elif line.startswith('export DOTFILES_PROFILE='):
                    profile = _unquote(line.split('=', 1)[1])
                elif line.startswith('export DOTFILES_OVERLAY='):
                    overlay = _unquote(line.split('=', 1)[1])
    return os_type, profile, overlay


def _find_dotfiles_dir():
    """Auto-detect the dotfiles repo root.

    Checks in order:
    1. $DOTFILES env var
    2. Parent of this file's directory (development mode — dotgarden/ is in the repo)
    3. Current working directory (pip-installed mode — user runs from their repo)
    """
    env_dir = os.environ.get('DOTFILES')
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)

    # Development mode: dotgarden/ is inside the repo
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.exists(os.path.join(parent, REGISTRY_FILENAME)):
        return parent

    # Pip-installed mode: look in cwd
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, REGISTRY_FILENAME)):
        return cwd

    # Fallback: ~/dotfiles
    home_dotfiles = os.path.join(os.path.expanduser('~'), 'dotfiles')
    if os.path.isdir(home_dotfiles):
        return home_dotfiles

    return cwd


def defaults():
    """Return default config dict.

    Returns dict with keys: dotfiles_dir, home_dir, registry_path.
    """
    dotfiles_dir = _find_dotfiles_dir()
    home_dir = os.path.expanduser('~')
    registry_path = os.path.join(dotfiles_dir, REGISTRY_FILENAME)
    return {
        'dotfiles_dir': dotfiles_dir,
        'home_dir': home_dir,
        'registry_path': registry_path,
    }
