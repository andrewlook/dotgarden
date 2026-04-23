"""Per-command modules for the `dotfile` CLI.

Each module exports a single `cmd_<name>` function that takes an argparse
Namespace and performs its subcommand. `cli.main` wires them into argparse.
"""

from dotgarden.cli.commands.bootstrap import cmd_bootstrap
from dotgarden.cli.commands.doctor import cmd_doctor
from dotgarden.cli.commands.env import cmd_env
from dotgarden.cli.commands.ids import cmd_ids
from dotgarden.cli.commands.list import cmd_list
from dotgarden.cli.commands.register import cmd_register
from dotgarden.cli.commands.specialize import cmd_specialize
from dotgarden.cli.commands.status import cmd_status
from dotgarden.cli.commands.unregister import cmd_unregister

__all__ = [
    'cmd_bootstrap',
    'cmd_doctor',
    'cmd_env',
    'cmd_ids',
    'cmd_list',
    'cmd_register',
    'cmd_specialize',
    'cmd_status',
    'cmd_unregister',
]
