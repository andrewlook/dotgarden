"""Logger + CLI color helpers.

- `LOG`: the package logger. Import-level configured once at module load.
- Color helpers: `color_label`, `color_hint`, `color_header` — named wrappers
  that hide the ANSI codes from call sites. Each returns plain ASCII when
  NO_COLOR is set or stdout isn't a tty.

Why named wrappers instead of passing ANSI constants around: the call site
reads as intent ("this is a label") rather than "this is a cyan-bold thing".
If the palette ever shifts, only this module changes.

The shared palette matches the rest of the CLI's visual style:
  label   — cyan + bold       ("what dotgarden is asking you")
  hint    — dim gray          ("defaults, bracketed values, helper text")
  header  — magenta + bold    ("section start")
"""

import logging
import os
import sys

LOG = logging.getLogger('dotfile')
LOG.setLevel(logging.INFO)
LOG.addHandler(logging.StreamHandler())


# ANSI escape codes — kept private. Call sites use the named wrappers below.
_ANSI_LABEL = '\033[1;36m'  # cyan + bold
_ANSI_HINT = '\033[2m'  # dim
_ANSI_HEADER = '\033[1;35m'  # magenta + bold
_ANSI_RESET = '\033[0m'


def _use_color(stream=None):
    """Whether to emit ANSI escapes to `stream`.

    Opt-out via the standard NO_COLOR env var (https://no-color.org/) and
    auto-off when not attached to a tty. Stream defaults to stdout since
    input()'s prompt writes there.
    """
    if os.environ.get('NO_COLOR'):
        return False
    stream = stream or sys.stdout
    return hasattr(stream, 'isatty') and stream.isatty()


def _wrap(text, code):
    """Lower-level wrapper — use the named helpers (color_label etc.) instead.

    Kept as an internal building block so we have one place that does the
    _use_color check and the reset.
    """
    if not _use_color():
        return text
    return f'{code}{text}{_ANSI_RESET}'


def color_label(text):
    """Cyan + bold — for "what dotgarden is asking" (prompts, question labels)."""
    return _wrap(text, _ANSI_LABEL)


def color_hint(text):
    """Dim gray — for helper text, bracketed defaults, aside parentheticals."""
    return _wrap(text, _ANSI_HINT)


def color_header(text):
    """Magenta + bold — for section headers (e.g. "Register — configure missing fields")."""
    return _wrap(text, _ANSI_HEADER)
