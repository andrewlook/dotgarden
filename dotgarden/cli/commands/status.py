"""`dotfile status` — symlink health check with OS/profile grouping."""

import os
from collections import OrderedDict

from dotgarden import config, paths, symlinks
from dotgarden import registry as reg

# Terminal colors for OS/profile tags (deterministic by sorted name).
# Uses 256-color palette for distinctness.
_TAG_COLORS = [
    '\033[38;5;141m',  # violet
    '\033[38;5;215m',  # peach/orange
    '\033[38;5;114m',  # green
    '\033[38;5;110m',  # teal
    '\033[38;5;217m',  # pink
    '\033[38;5;180m',  # tan
]
_RESET = '\033[0m'
_DIM = '\033[2m'

# Main-repo color for `repo:` banner line and `~/dotfiles/...` target paths.
# Picked to stay distinct from _TAG_COLORS so profile tags don't clash with it.
_REPO_COLOR = '\033[38;5;75m'  # sky blue


def _entry_group_key(entry):
    """Return (group_label, condition_type, condition_value) for an entry."""
    if entry.get('managed_by') == 'bootstrap':
        os_type = entry.get('os')
        profile_val = entry.get('profile')
        if profile_val:
            return f'bootstrap ({profile_val})'
        elif os_type:
            return f'bootstrap ({os_type})'
        else:
            return 'bootstrap'
    return entry.get('category') or 'registered'


def _config_categories(registry):
    """Derive .config categories from registry entries whose source is under ~/.config/."""
    cats = set()
    for entry in registry.get('registered_files', []):
        src = entry.get('source_path', '')
        if src.startswith('~/.config/'):
            cat = entry.get('category')
            if cat:
                cats.add(cat)
    return cats


def _tag_color(name, all_names):
    """Get a deterministic color for a tag name based on alphabetical position."""
    idx = sorted(all_names).index(name) % len(_TAG_COLORS)
    return _TAG_COLORS[idx]


def _format_tag(condition_type, condition_value, all_conditions):
    """Format a colored [macos] or [work] tag."""
    color = _tag_color(f'{condition_type}:{condition_value}', all_conditions)
    return f'{color}[{condition_value}]{_RESET}'


def _group_sort_key(group_name, config_cats, conditioned_groups):
    """Sort key: bootstrap, bootstrap-os/profile, .config(uncond then cond), other(uncond then cond)."""
    is_cond = group_name in conditioned_groups
    if group_name == 'bootstrap':
        return (0, 0, '')
    if group_name.startswith('bootstrap ('):
        return (1, 0, group_name)
    if group_name in config_cats:
        return (2, 1 if is_cond else 0, group_name)
    return (3, 1 if is_cond else 0, group_name)


def _get_group_condition(group_name):
    """Extract (condition_type, condition_value) from a group name, or None."""
    if not group_name.startswith('bootstrap ('):
        return None
    inner = group_name[len('bootstrap (') : -1]
    if inner in config.DEFAULT_OS_NAMES:
        return ('os', inner)
    if inner in config.DEFAULT_PROFILES:
        return ('profile', inner)
    return ('profile', inner)  # default to profile for unknown


def _find_shared_dir_prefix(paths_list):
    """Find the shared directory prefix of a list of paths, if meaningful.

    Returns the prefix (with trailing /) or None if no meaningful shared prefix.
    Only returns a prefix that contains at least one '/' beyond ~/ (i.e. at least
    one directory level deeper than home).
    """
    if len(paths_list) < 2:
        return None
    prefix = os.path.commonprefix(paths_list)
    if '/' in prefix:
        prefix = prefix[: prefix.rindex('/') + 1]
    else:
        return None
    if prefix in ('~/', ''):
        return None
    return prefix


def _colorize_target(target_str, dotfiles_tilde, overlay_tilde, overlay_color):
    """Color only the base-directory prefix of a target path.

    Just the `~/dotfiles` prefix (or the overlay equivalent) is colored, so
    the repo identity stands out without tinting the path inside the repo.
    """
    if target_str == dotfiles_tilde:
        return f'{_REPO_COLOR}{target_str}{_RESET}'
    if target_str.startswith(dotfiles_tilde + '/'):
        return f'{_REPO_COLOR}{dotfiles_tilde}{_RESET}{target_str[len(dotfiles_tilde) :]}'
    if overlay_tilde and overlay_color:
        if target_str == overlay_tilde:
            return f'{overlay_color}{target_str}{_RESET}'
        if target_str.startswith(overlay_tilde + '/'):
            return (
                f'{overlay_color}{overlay_tilde}{_RESET}'
                f'{target_str[len(overlay_tilde) :]}'
            )
    return target_str


def _print_header_banner(repo_tilde, overlay_tilde, overlay_color, overlay_missing):
    """Print the boxed `repo:` / `overlay:` banner at the top of status output."""
    plain_lines = [f'{"repo:":<8} {repo_tilde}']
    if overlay_tilde:
        plain_lines.append(f'{"overlay:":<8} {overlay_tilde}')
    width = max(max(len(line) for line in plain_lines), 30)
    bar = '-' * width

    print(bar)
    print(f'{_REPO_COLOR}{"repo:":<8} {repo_tilde}{_RESET}')
    if overlay_tilde:
        color = overlay_color or ''
        suffix = ' \033[33m(missing)\033[0m' if overlay_missing else ''
        reset = _RESET if color else ''
        print(f'{color}{"overlay:":<8} {overlay_tilde}{reset}{suffix}')
    print(bar)
    print()


def _print_entry_rows(
    entries,
    dotfiles_dir,
    indent='    ',
    local_statuses=None,
    *,
    dotfiles_tilde='~/dotfiles',
    overlay_tilde=None,
    overlay_color=None,
):
    """Print symlink status rows with inline .local indicator. Returns True if all ok."""
    all_ok = True
    rows = []
    for entry in entries:
        status, source, target, is_ok = symlinks.check_status(entry, dotfiles_dir)
        rows.append((entry, status, source, target, is_ok))
        if not is_ok:
            all_ok = False

    sources = [s for _, _, s, _, _ in rows]
    shared_prefix = _find_shared_dir_prefix(sources) if len(sources) > 1 else None

    if shared_prefix:
        escaped_prefix = paths.escape_spaces(shared_prefix)
        print(f'{indent}\033[36m{escaped_prefix}\033[0m')
        row_indent = indent + '  '
    else:
        row_indent = indent

    for entry, status, source, target, is_ok in rows:
        if shared_prefix and source.startswith(shared_prefix):
            display_source = source[len(shared_prefix) :]
        else:
            display_source = source

        escaped_source = paths.escape_spaces(display_source)
        target_display = _colorize_target(
            paths.escape_spaces(target), dotfiles_tilde, overlay_tilde, overlay_color
        )
        colored_source = f'\033[36m{escaped_source}\033[0m'

        if shared_prefix:
            stripped = [
                s[len(shared_prefix) :] for _, _, s, _, _ in rows if s.startswith(shared_prefix)
            ]
            max_src = max(len(s) for s in stripped) if stripped else 0
            padding = max_src - len(display_source)
        else:
            max_src = max(len(s) for _, _, s, _, _ in rows) if rows else 0
            padding = max_src - len(source)

        if is_ok:
            print(f'{row_indent}{colored_source}{" " * padding}  ->  {target_display}')
        else:
            colored_status = f'\033[31m{status}\033[0m'
            print(
                f'{row_indent}{colored_source}{" " * padding}  ->  {target_display}  {colored_status}'
            )

        if local_statuses is not None:
            entry_source = entry.get('source_path', '')
            if not entry_source.startswith('~/'):
                continue
            basename = entry_source[2:]
            if not basename.startswith('.'):
                basename = '.' + basename
            info = local_statuses.get(basename)
            if info:
                local_statuses.pop(basename)
                local_ok = (
                    info['local_exists'] and info['local_fresh'] and info['base_includes_local']
                )
                mark = f'{_DIM}✓{_RESET}' if local_ok else '\033[33m⚠\033[0m'
                print(f'{row_indent}  {mark} {_DIM}{info["local_name"]}{_RESET}')
                if info['issues']:
                    all_ok = False

    return all_ok


def _print_variant_chain(entry, local_statuses, indent='    '):
    """Print the inclusion chain under an OS/profile variant entry."""
    entry_source = entry.get('source_path', '')
    if not entry_source.startswith('~/'):
        return
    variant_name = entry_source[2:]

    matched_os = config.is_os_specific(variant_name)
    matched_profile = config.is_profile_specific(variant_name)
    if matched_os:
        base = variant_name[len(f'.{matched_os}.') :]
        if not base.startswith('.'):
            base = '.' + base
    elif matched_profile:
        base = variant_name[len(f'.{matched_profile}.') :]
        if not base.startswith('.'):
            base = '.' + base
    else:
        return

    local_name = f'{base}.local'

    info = local_statuses.get(base) if local_statuses else None
    if info:
        chain_ok = info['local_exists'] and info['base_includes_local']
        mark = f'{_DIM}✓{_RESET}' if chain_ok else '\033[33m⚠\033[0m'
        print(f'{indent}  {mark} {_DIM}~/{variant_name} <- ~/{local_name} <- ~/{base}{_RESET}')


def cmd_status(args):
    """Check status of all managed symlinks (registered + bootstrap-managed)."""
    cfg = config.defaults()
    dotfiles_dir = cfg['dotfiles_dir']
    home_dir = cfg['home_dir']
    registry_path = cfg['registry_path']

    registry = reg.load(registry_path)
    bootstrap_entries = symlinks.discover_bootstrap_managed(dotfiles_dir, home_dir, registry)

    os_type, profile, overlay_dir = config.read_dotfiles_env(home_dir)
    overlay_abs = os.path.expanduser(overlay_dir) if overlay_dir else None
    overlay_exists = overlay_abs is not None and os.path.isdir(overlay_abs)
    overlay_profile_name = None
    if overlay_exists:
        try:
            overlay_profile_name = symlinks._read_overlay_profile(overlay_abs)
        except reg.RegistryError:
            pass

    filtered_registered = []
    for entry in registry['registered_files']:
        entry_os = entry.get('os')
        entry_profile = entry.get('profile')
        if entry_os and os_type and entry_os != os_type:
            continue
        if entry_profile and profile and entry_profile != profile:
            continue
        filtered_registered.append(entry)

    overlay_entries = symlinks.discover_overlay_managed(overlay_abs, home_dir, os_type)

    all_entries = bootstrap_entries + filtered_registered + overlay_entries

    if not all_entries:
        print('No managed files.')
        return

    groups = OrderedDict()
    for entry in all_entries:
        key = _entry_group_key(entry)
        groups.setdefault(key, []).append(entry)

    config_cats = _config_categories(registry)

    all_good = True

    local_statuses = {}
    all_local_statuses = {}
    if os_type:
        for info in symlinks.get_local_status(
            dotfiles_dir, home_dir, os_type, profile, overlay_dir=overlay_abs
        ):
            local_statuses[info['dotfile']] = info
            all_local_statuses[info['dotfile']] = info

    all_conditions = set()
    for entry in registry['registered_files']:
        if entry.get('os'):
            all_conditions.add(f'os:{entry["os"]}')
        if entry.get('profile'):
            all_conditions.add(f'profile:{entry["profile"]}')
    for gn in groups:
        cond = _get_group_condition(gn)
        if cond:
            all_conditions.add(f'{cond[0]}:{cond[1]}')
    # Seed overlay profile so _tag_color can resolve it even when the overlay
    # contributes no entries in the current OS slice.
    if overlay_profile_name:
        all_conditions.add(f'profile:{overlay_profile_name}')

    overlay_color = None
    if overlay_profile_name:
        overlay_color = _tag_color(f'profile:{overlay_profile_name}', all_conditions)

    dotfiles_tilde = paths.format_for_display(dotfiles_dir, home_dir)
    overlay_tilde = (
        paths.format_for_display(overlay_abs, home_dir) if overlay_abs else None
    )
    _print_header_banner(
        dotfiles_tilde,
        overlay_tilde,
        overlay_color,
        overlay_missing=bool(overlay_dir) and not overlay_exists,
    )

    conditioned_groups = set()
    for gn, entries in groups.items():
        if gn.startswith('bootstrap ('):
            conditioned_groups.add(gn)
            continue
        os_vals = {e.get('os') for e in entries if e.get('os')}
        prof_vals = {e.get('profile') for e in entries if e.get('profile')}
        if (len(os_vals) == 1 and not prof_vals) or (len(prof_vals) == 1 and not os_vals):
            conditioned_groups.add(gn)

    sorted_groups = sorted(
        groups.items(), key=lambda kv: _group_sort_key(kv[0], config_cats, conditioned_groups)
    )

    in_config_section = False
    prev_section = None

    for group_name, entries in sorted_groups:
        cond = _get_group_condition(group_name)
        if not cond and group_name in conditioned_groups:
            os_vals = {e.get('os') for e in entries if e.get('os')}
            prof_vals = {e.get('profile') for e in entries if e.get('profile')}
            if os_vals:
                cond = ('os', os_vals.pop())
            elif prof_vals:
                cond = ('profile', prof_vals.pop())

        if group_name == 'bootstrap':
            section = 0
        elif group_name.startswith('bootstrap ('):
            section = 1
        elif group_name in config_cats:
            section = 2
        else:
            section = 3

        if prev_section is not None:
            if section != prev_section:
                print()
                print()
            else:
                print()
        prev_section = section

        if cond:
            tag = _format_tag(cond[0], cond[1], all_conditions)
            display_name = group_name.split('(')[0].strip() if '(' in group_name else group_name
        else:
            tag = ''
            display_name = group_name
        if display_name == 'bootstrap':
            display_name = '$HOME'

        if group_name in config_cats:
            if not in_config_section:
                in_config_section = True
                print(f'  {_DIM}.config{_RESET}')
            if tag:
                print(f'    {tag} {_DIM}{display_name}{_RESET}')
            else:
                print(f'    {_DIM}{display_name}{_RESET}')
        else:
            in_config_section = False
            if tag:
                print(f'  {tag} {_DIM}{display_name}{_RESET}')
            else:
                print(f'  {_DIM}{display_name}{_RESET}')

        indent = '      ' if group_name in config_cats else '    '

        if cond:
            if not _print_entry_rows(
                entries,
                dotfiles_dir,
                indent,
                dotfiles_tilde=dotfiles_tilde,
                overlay_tilde=overlay_tilde,
                overlay_color=overlay_color,
            ):
                all_good = False
            for entry in entries:
                _print_variant_chain(entry, all_local_statuses, indent)
        else:
            if not _print_entry_rows(
                entries,
                dotfiles_dir,
                indent,
                local_statuses,
                dotfiles_tilde=dotfiles_tilde,
                overlay_tilde=overlay_tilde,
                overlay_color=overlay_color,
            ):
                all_good = False

    if local_statuses:
        print()
        print(f'  {_DIM}local overrides{_RESET}')
        for info in local_statuses.values():
            local_ok = info['local_exists'] and info['local_fresh'] and info['base_includes_local']
            mark = f'{_DIM}✓{_RESET}' if local_ok else '\033[33m⚠\033[0m'
            print(f'    {mark} {_DIM}{info["local_name"]}{_RESET}')
            if info['issues']:
                all_good = False

    if not os_type:
        print()
        print(f'  {_DIM}local overrides{_RESET}')
        print(f'    {_DIM}⚠ skipped — run `dotfile bootstrap --os <os>` to enable{_RESET}')

    print()
    if all_good:
        print('All managed files are healthy.')
    else:
        fix_cmd = 'dotfile bootstrap'
        if os_type:
            fix_cmd += f' --os {os_type}'
        if profile:
            fix_cmd += f' --profile {profile}'
        print(f'Some issues found. Run `{fix_cmd}` to fix.')
