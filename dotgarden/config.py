"""Shared constants and environment configuration for dotfiles management."""

import os

REGISTRY_FILENAME = '__registry__.yaml'

# Directory at the dotfiles repo root whose top-level children auto-map to
# ~/.config/<name>. A convention-over-configuration alternative to registering
# each `_fish/`, `_ghostty/`, `_zed/` entry explicitly — see the Unit 1 plan
# in docs/plans/2026-04-22-001-...-plan.md.
DOT_CONFIG_DIR = '.config'

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


def parse_nested_variant(filename, os_names=None, profiles=None):
    """Parse a filename inside `.config/<tool>/` for a variant modifier.

    Nested variants use BASE.MOD.EXT format (e.g. `config.macos.fish`,
    `config.work.fish`), distinct from the root-level `.MOD.BASE` pattern.
    Extensionless bases like ghostty's `config` use BASE.MOD (e.g.
    `config.macos`).

    Returns a tuple (base_filename, modifier_kind, modifier_value) if the
    filename is a variant, where modifier_kind is 'os' or 'profile'.
    Returns None for plain files (no modifier detected).

    Examples (with default os_names=['macos','linux'], profiles=['work','home']):
        'config.fish'         → None (plain file, 'fish' is not an OS/profile)
        'config.macos.fish'   → ('config.fish', 'os', 'macos')
        'config.work.fish'    → ('config.fish', 'profile', 'work')
        'config.macos'        → ('config', 'os', 'macos')        (extensionless)
        'init.lua'            → None
        'init.work.lua'       → ('init.lua', 'profile', 'work')
    """
    if os_names is None:
        os_names = DEFAULT_OS_NAMES
    if profiles is None:
        profiles = DEFAULT_PROFILES
    parts = filename.split('.')
    if len(parts) < 2:
        return None

    def _classify(segment):
        if segment in os_names:
            return 'os'
        if segment in profiles:
            return 'profile'
        return None

    # Last-segment modifier (extensionless case: `config.macos`).
    last_kind = _classify(parts[-1])
    if last_kind and len(parts) == 2:
        return ('.'.join(parts[:-1]), last_kind, parts[-1])

    # Penultimate-segment modifier (with extension: `config.macos.fish`).
    if len(parts) >= 3:
        mid_kind = _classify(parts[-2])
        if mid_kind:
            base = '.'.join(parts[:-2] + parts[-1:])
            return (base, mid_kind, parts[-2])

    return None


# Tool-type detection for .local file generation.
# Maps dotfile basenames (root convention) to the syntax family used for
# inclusion. Nested bases under .config/<tool>/ are matched by extension
# or sub-path via `get_tool_type()`.
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


def get_tool_type(base_path):
    """Determine the inclusion tool type for a base dotfile path.

    Returns one of the tool-type strings ('shell', 'git', 'tmux', 'fish', …),
    or None when no include syntax is known — callers should treat None as
    "unsupported inclusion" and surface it (Unit 5).

    Resolution order:
    1. Exact match in `LOCAL_TOOL_TYPES` (root-level dotfiles).
    2. Nested .config/<tool>/<base> patterns matched by file extension:
       - `.fish` → 'fish'
    """
    if base_path in LOCAL_TOOL_TYPES:
        return LOCAL_TOOL_TYPES[base_path]
    # Nested path — match by extension.
    if base_path.endswith('.fish'):
        return 'fish'
    return None


def format_local_include(tool_type, variant_filename):
    """Return the inclusion line for a variant file, per tool type.

    variant_filename can be:
    - repo-relative (e.g. `.macos.zprofile` or `.config/fish/config.macos.fish`)
      → emitted as `~/<path>` so the runtime resolves against $HOME
    - absolute (starts with `/`, e.g. overlay-sourced variants)
      → emitted as-is
    - already home-relative (starts with `~/`)
      → emitted as-is

    The git tool type uses `path = <variant>` directly (not shell-style
    expansion), which git resolves relative to the including file.
    """
    if variant_filename.startswith('/') or variant_filename.startswith('~/'):
        runtime_path = variant_filename
    else:
        runtime_path = f'~/{variant_filename}'
    if tool_type == 'shell':
        return f'[[ -f {runtime_path} ]] && . {runtime_path}'
    elif tool_type == 'git':
        return f'[include]\n    path = {variant_filename}'
    elif tool_type == 'tmux':
        return f'source-file -q {runtime_path}'
    elif tool_type == 'fish':
        return f'test -e {runtime_path}; and source {runtime_path}'
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
