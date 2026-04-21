"""`dotfile env` — print current OS, profile, and overlay from .dotfiles_env."""

from dotgarden import config


def cmd_env(args):
    """Print current OS, profile, and overlay from ~/.dotfiles_env."""
    cfg = config.defaults()
    home_dir = cfg['home_dir']
    os_type, profile_val, overlay = config.read_dotfiles_env(home_dir)
    if os_type:
        print(f'os: {os_type}')
    else:
        print('os: (not set)')
    if profile_val:
        print(f'profile: {profile_val}')
    else:
        print('profile: (not set)')
    if overlay:
        print(f'overlay: {overlay}')
    if not os_type:
        print('\nRun `dotfile bootstrap --os <os>` to initialize.')
