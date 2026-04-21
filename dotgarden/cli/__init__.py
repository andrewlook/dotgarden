"""dotgarden.cli — the `dotfile` command.

Runtime entry point is `main`, dispatched to per-subcommand handlers in
`dotgarden.cli.commands`. Tests and the PyPI entry-point script both import
from `dotgarden.cli` directly, so this `__init__` re-exports the public
surface:

  from dotgarden.cli import main           # pyproject entry-point
  from dotgarden.cli import cmd_register   # tests, library users
  from dotgarden.cli import cmd_bootstrap  # …
"""

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
from dotgarden.cli.main import _apply_dotfile_home_override, main

__all__ = [
    '_apply_dotfile_home_override',
    'cmd_bootstrap',
    'cmd_doctor',
    'cmd_env',
    'cmd_ids',
    'cmd_list',
    'cmd_register',
    'cmd_status',
    'cmd_unregister',
    'main',
]
