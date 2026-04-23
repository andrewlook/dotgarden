"""`dotfile specialize` — scaffold OS/profile variant files for a dotfile.

Two forms:
  dotfile specialize os <path>
  dotfile specialize profile <path>

Root-level `<path>` (e.g. `.gitconfig`) creates root-convention variants:
  .macos.gitconfig, .linux.gitconfig — per the registry's `os:` list
  .work.gitconfig, .home.gitconfig   — per the registry's `profiles:` list

Nested `<path>` under `.config/<tool>/` (e.g. `.config/fish/config.fish`)
creates nested-convention variants in the same directory:
  .config/fish/config.macos.fish, .config/fish/config.linux.fish
  .config/fish/config.work.fish,  .config/fish/config.home.fish

In both cases the base file is appended with an include line for its
`.local` file (using the tool-type-appropriate syntax), unless such a
line is already present. Running again is a no-op on existing files.
"""

import os
import sys

from dotgarden import config, registry as reg
from dotgarden.cli.utils.logging import LOG


def _is_nested_path(dotfile):
    """True when the given repo-relative path lives under .config/<tool>/."""
    return dotfile.startswith(f'{config.DOT_CONFIG_DIR}/') and dotfile.count('/') >= 2


def _variant_name(dotfile, modifier, is_nested):
    """Build a variant filename per the appropriate convention.

    Root: `.macos.gitconfig` (leading-dot + modifier + basename)
    Nested: `.config/fish/config.macos.fish` (dir + BASE.MOD.EXT)
    """
    if not is_nested:
        # Root convention: .PROFILE.BASE. Input dotfile already has leading dot.
        return f'.{modifier}{dotfile}'
    # Nested: split the basename around the last dot and insert the modifier.
    dir_part, basename = os.path.split(dotfile)
    if '.' in basename:
        stem, ext = basename.rsplit('.', 1)
        return f'{dir_part}/{stem}.{modifier}.{ext}'
    # Extensionless base (e.g. ghostty `config`): append modifier as suffix.
    return f'{dir_part}/{basename}.{modifier}'


def _local_path(dotfile, is_nested):
    """Where the `.local` file lives relative to the repo root.

    Root: `<dotfile>.local` at repo root.
    Nested: `<dir>/<base>.local` in the same dir as the base file.
    """
    if is_nested:
        return f'{dotfile}.local'
    # Root: also <dotfile>.local, but kept separate for documentation parity.
    return f'{dotfile}.local'


def cmd_specialize(args):
    """Add OS or profile variant files for a dotfile."""
    cfg = config.defaults()
    dotfiles_dir = cfg['dotfiles_dir']
    registry_path = cfg['registry_path']
    registry = reg.load(registry_path)

    kind = args.kind  # 'os' or 'profile'
    dotfile = args.dotfile

    # Normalize the input. Nested paths stay as-is; root paths need a leading dot.
    is_nested = _is_nested_path(dotfile)
    if not is_nested and not dotfile.startswith('.'):
        dotfile = '.' + dotfile

    dotfile_path = os.path.join(dotfiles_dir, dotfile)
    if not os.path.exists(dotfile_path):
        LOG.error(f'Dotfile not found: {dotfile}')
        sys.exit(1)

    if kind == 'os':
        modifiers = registry.get('os') or config.DEFAULT_OS_NAMES
    else:
        modifiers = registry.get('profiles') or config.DEFAULT_PROFILES

    tool_type = config.get_tool_type(dotfile)
    if tool_type is None:
        LOG.error(
            f'No known include syntax for {dotfile!r}. Add the tool type '
            f'to LOCAL_TOOL_TYPES / get_tool_type in dotgarden/config.py, '
            f'or specialize a different base.'
        )
        sys.exit(1)

    local_name = _local_path(dotfile, is_nested)
    # format_local_include emits the runtime source/include line — but
    # specialize appends it to the base file at repo-root, where the
    # reference needs to be relative to the base. Strip the leading `~/`
    # (if shell/fish/tmux) so the include resolves at fish/shell load time
    # against the right directory.
    include_line = config.format_local_include(tool_type, local_name)

    # Preview which variant files will be created.
    created_files = []
    for modifier in modifiers:
        variant = _variant_name(dotfile, modifier, is_nested)
        variant_path = os.path.join(dotfiles_dir, variant)
        if os.path.exists(variant_path):
            print(f'  \033[2m✓ {variant} (exists)\033[0m')
        else:
            created_files.append((variant, variant_path))
            print(f'  \033[32m+ {variant}\033[0m')

    # Check base file for existing include.
    with open(dotfile_path, 'r') as f:
        base_contents = f.read()
    needs_include = local_name not in base_contents

    if needs_include:
        print(f'  \033[33m~ {dotfile} (add {local_name} include)\033[0m')

    if not created_files and not needs_include:
        print(f'\n{dotfile} is already specialized for {kind}.')
        return

    if args.dry_run:
        print(f'\n[DRY RUN] Would create {len(created_files)} file(s). No changes made.')
        return

    for variant, variant_path in created_files:
        os.makedirs(os.path.dirname(variant_path) or dotfiles_dir, exist_ok=True)
        with open(variant_path, 'w') as f:
            f.write(f'# {kind}-specific overrides for {dotfile}\n')
        print(f'  Created {variant}')

    if needs_include:
        with open(dotfile_path, 'a') as f:
            f.write(f'\n{include_line}\n')
        print(f'  Added {local_name} include to {dotfile}')

    print(
        f'\n✓ Specialized {dotfile} for {kind}. '
        f'Run `dotfile bootstrap` to generate {local_name}.'
    )
