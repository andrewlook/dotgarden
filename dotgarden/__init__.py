"""dotgarden — dotfile registry and bootstrap.

Most users consume this package through the `dotfile` CLI. Library users can
import the core primitives directly:

    from dotgarden import bootstrap, read_dotfiles_env
"""

from importlib.metadata import PackageNotFoundError, version

from dotgarden.config import read_dotfiles_env
from dotgarden.symlinks import bootstrap, discover_bootstrap_managed

try:
    __version__ = version('dotgarden')
except PackageNotFoundError:
    # Running from a source checkout without an install (rare). The CLI
    # still works; only `dotfile --version` reports this fallback string.
    __version__ = '0+unknown'

__all__ = ['__version__', 'bootstrap', 'discover_bootstrap_managed', 'read_dotfiles_env']
