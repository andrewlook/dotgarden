"""dotgarden — dotfile registry and bootstrap.

Most users consume this package through the `dotfile` CLI. Library users can
import the core primitives directly:

    from dotgarden import bootstrap, read_dotfiles_env
"""

from dotgarden.config import read_dotfiles_env
from dotgarden.symlinks import bootstrap, discover_bootstrap_managed

__all__ = ['bootstrap', 'discover_bootstrap_managed', 'read_dotfiles_env']
