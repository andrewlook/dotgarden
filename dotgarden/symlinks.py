"""Symlink operations, file discovery, and bootstrap logic."""

import logging
import os
import shutil

import yaml

from dotgarden import registry as reg
from dotgarden.config import (
    LOCAL_TOOL_TYPES,
    NOT_DOTFILES,
    NOT_DOTFILES_EXTENSIONS,
    REGISTRY_FILENAME,
    format_local_include,
    is_os_specific,
    is_profile_specific,
    read_dotfiles_env,
)

LOG = logging.getLogger(__name__)


def list_dotfiles(directory, exclude=None):
    """List files in a directory, excluding non-dotfiles.

    Returns sorted list of filenames.
    """
    if exclude is None:
        exclude = NOT_DOTFILES
    result = []
    if not os.path.isdir(directory):
        return result
    for fname in os.listdir(directory):
        full_path = os.path.join(directory, fname)
        if os.path.isfile(full_path) and fname not in exclude:
            if any(fname.endswith(ext) for ext in NOT_DOTFILES_EXTENSIONS):
                continue
            result.append(fname)
    return sorted(result)


def prepare_symlink_target(target, link):
    """Prepare a symlink destination, backing up any existing file.

    Returns a string indicating what happened:
      'needed'  - link didn't exist, ready to create
      'ok'      - link already points to correct target
      'stale'   - link was a dead symlink, removed it
      'replaced' - link pointed elsewhere or was a regular file, backed up and removed

    Side effects: backs up and removes conflicting files at `link`.
    """
    if os.path.islink(link):
        old_target = os.path.realpath(os.readlink(link))
        abs_target = os.path.realpath(target)
        if abs_target == old_target:
            return 'ok'
        if not os.path.exists(link):
            # Dead symlink — just remove, no backup needed
            os.unlink(link)
            return 'stale'
        # Live symlink pointing elsewhere — back up and remove
        bakfile = link + '.bak'
        if os.path.isdir(link):
            if os.path.exists(bakfile):
                shutil.rmtree(bakfile)
            shutil.copytree(link, bakfile, symlinks=True)
            shutil.rmtree(link)
        else:
            shutil.copyfile(link, bakfile)
            os.remove(link)
        return 'replaced'

    if not os.path.exists(link):
        return 'needed'

    # Regular file or directory — back up and remove
    bakfile = link + '.bak'
    if os.path.isdir(link):
        if os.path.exists(bakfile):
            shutil.rmtree(bakfile)
        shutil.copytree(link, bakfile, symlinks=True)
        shutil.rmtree(link)
    else:
        shutil.copyfile(link, bakfile)
        os.remove(link)
    return 'replaced'


def create_symlink(target, link):
    """Create a symlink, creating parent directories as needed."""
    parent = os.path.dirname(link)
    if parent and not os.path.exists(parent):
        os.makedirs(parent)
    os.symlink(target, link)


def check_status(entry, dotfiles_dir):
    """Check symlink status of a single entry.

    Returns (status_str, source_display, target_display, is_ok).
    """
    source_path = os.path.expanduser(entry['source_path'])
    repo_path = os.path.join(dotfiles_dir, entry['repo_path'])
    source_display = entry['source_path']

    from dotgarden.paths import format_for_display

    home_dir = os.path.expanduser('~')
    target_display = format_for_display(repo_path, home_dir)

    # Trailing slash for directories
    if os.path.isdir(repo_path):
        if not source_display.endswith('/'):
            source_display += '/'
        if not target_display.endswith('/'):
            target_display += '/'

    if not os.path.exists(repo_path):
        return ('✗ MISSING', source_display, target_display, False)

    if not os.path.exists(source_path) and not os.path.islink(source_path):
        return ('⚠ UNLINKED', source_display, target_display, False)

    if not os.path.islink(source_path):
        return ('⚠ NOT SYMLINK', source_display, target_display, False)

    target = os.path.realpath(os.readlink(source_path))
    expected = os.path.realpath(repo_path)
    if target != expected:
        return ('✗ WRONG TARGET', source_display, target_display, False)

    return ('✓', source_display, target_display, True)


def discover_bootstrap_managed(dotfiles_dir, home_dir, registry_data):
    """Discover all files managed by bootstrap (not in registry).

    Returns list of entry dicts with managed_by='bootstrap'.
    """
    os_type, profile, _overlay = read_dotfiles_env(home_dir)
    registered_repo_paths = {e['repo_path'] for e in registry_data.get('registered_files', [])}
    exclude_files = list(NOT_DOTFILES) + list(registry_data.get('ignore_files') or [])

    entries = []

    # Root dotfiles (filter out OS/profile variants for other systems)
    for fname in list_dotfiles(dotfiles_dir, exclude=exclude_files):
        file_os = is_os_specific(fname)
        file_profile = is_profile_specific(fname)
        if file_os and file_os != os_type:
            continue
        if file_profile and file_profile != profile:
            continue
        repo_path = fname
        if repo_path in registered_repo_paths:
            continue
        entries.append(
            {
                'id': f'(bootstrap) {fname}',
                'source_path': f'~/{fname}',
                'repo_path': repo_path,
                'category': None,
                'os': file_os,
                'profile': file_profile,
                'managed_by': 'bootstrap',
            }
        )

    # OS-specific files
    if os_type:
        os_dir = os.path.join(dotfiles_dir, f'__{os_type}__')
        for fname in list_dotfiles(os_dir, exclude=exclude_files):
            repo_path = f'__{os_type}__/{fname}'
            if repo_path in registered_repo_paths:
                continue
            entries.append(
                {
                    'id': f'(bootstrap) {fname}',
                    'source_path': f'~/{fname}',
                    'repo_path': repo_path,
                    'category': None,
                    'os': os_type,
                    'profile': None,
                    'managed_by': 'bootstrap',
                }
            )

    # Profile-specific files
    if profile:
        profile_dir = os.path.join(dotfiles_dir, f'__{profile}__')
        for fname in list_dotfiles(profile_dir, exclude=exclude_files):
            repo_path = f'__{profile}__/{fname}'
            if repo_path in registered_repo_paths:
                continue
            entries.append(
                {
                    'id': f'(bootstrap) {fname}',
                    'source_path': f'~/{fname}',
                    'repo_path': repo_path,
                    'category': None,
                    'os': None,
                    'profile': profile,
                    'managed_by': 'bootstrap',
                }
            )

    return entries


def _read_overlay_profile(overlay_dir):
    """Load the overlay's `__registry__.yaml` and return its declared profile.

    Every overlay must contain a registry file with `profile: <name>` at the
    top, even if there are no registered entries. Raises RegistryError if the
    file is missing or the profile field is absent — the caller (bootstrap
    / cmd_bootstrap) is expected to let the error propagate so the user
    sees a clear message.
    """
    reg_path = os.path.join(overlay_dir, REGISTRY_FILENAME)
    if not os.path.exists(reg_path):
        raise reg.RegistryError(
            f'Overlay at {overlay_dir} is missing {REGISTRY_FILENAME}. '
            f'Every overlay must declare its profile scope — create '
            f'{REGISTRY_FILENAME} with at least:\n'
            "    version: '3.0'\n"
            '    profile: <name>'
        )
    data = reg.load(reg_path)
    return reg.get_overlay_profile(data, reg_path)


def _compose_exclude_files(dotfiles_dir, overlay_dir):
    """Build the full list of filenames to skip when listing dotfiles.

    Combines the package defaults (NOT_DOTFILES) with any `ignore_files`
    entries declared in the main and/or overlay registry.
    """
    extra = set()
    for source_dir in (dotfiles_dir, overlay_dir):
        if not source_dir:
            continue
        reg_path = os.path.join(source_dir, REGISTRY_FILENAME)
        if not os.path.exists(reg_path):
            continue
        try:
            reg_data = reg.load(reg_path)
        except (reg.RegistryError, yaml.YAMLError, KeyError):
            continue
        extra.update(reg_data.get('ignore_files') or [])
    return list(NOT_DOTFILES) + sorted(extra)


def _write_dotfiles_env(home_dir, os_type, profile, overlay_dir):
    """Rewrite ~/.dotfiles_env, preserving any user-added export lines.

    Only lines starting with the managed prefixes (DOTFILES_OS/PROFILE/OVERLAY)
    and the shebang are replaced. Everything else round-trips.
    """
    path = os.path.join(home_dir, '.dotfiles_env')
    managed = ('export DOTFILES_OS=', 'export DOTFILES_PROFILE=', 'export DOTFILES_OVERLAY=')
    preserved = []
    if os.path.exists(path):
        with open(path) as f:
            for raw in f:
                stripped = raw.rstrip('\n')
                s = stripped.strip()
                if s.startswith('#!') or s.startswith(managed):
                    continue
                preserved.append(stripped)
    while preserved and preserved[-1] == '':
        preserved.pop()

    lines = ['#!/bin/bash', f'export DOTFILES_OS={os_type}']
    if profile:
        lines.append(f'export DOTFILES_PROFILE={profile}')
    if overlay_dir:
        lines.append(f'export DOTFILES_OVERLAY={overlay_dir}')
    if preserved:
        lines.append('')
        lines.extend(preserved)
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def _check_link_state(abs_link, abs_real):
    """Return the dry-run action label for a link at abs_link → abs_real."""
    if os.path.islink(abs_link):
        old = os.path.abspath(os.readlink(abs_link))
        if old == os.path.abspath(abs_real):
            return 'ok'
        if not os.path.exists(abs_link):
            return 'would_repair'
        return 'would_update'
    if os.path.exists(abs_link):
        return 'would_update'
    return 'would_create'


def _apply_link(abs_link, abs_real, phase, dry_run, results):
    """Create a symlink (or record the plan in dry-run). Appends one result."""
    if dry_run:
        results.append((_check_link_state(abs_link, abs_real), abs_link, abs_real, phase))
        return
    status = prepare_symlink_target(abs_real, abs_link)
    if status == 'ok':
        results.append(('ok', abs_link, abs_real, phase))
        return
    action = 'repaired' if status == 'stale' else 'created'
    create_symlink(abs_real, abs_link)
    results.append((action, abs_link, abs_real, phase))


def _link_root_dotfiles(
    source_dir,
    home_dir,
    phase,
    os_type,
    profile,
    exclude_files,
    dry_run,
    results,
    *,
    rename_prefix=None,
    reject_variants=False,
):
    """Link root-level dotfiles from source_dir to home_dir, filtering by variant.

    Returns the list of filenames actually linked — callers need this to detect
    conflicts between common dotfiles and __os__/__profile__ variant dirs.

    Overlay-specific kwargs (unused for main-repo linking):
      rename_prefix    — when set (e.g. '.work'), the link target in home_dir
                         is renamed: bare '.gitconfig' becomes '.work.gitconfig'.
                         Used so overlay files carry the overlay's declared
                         profile implicitly, without needing a filename prefix
                         inside the overlay repo itself.
      reject_variants  — when True, any filename with an OS or profile prefix
                         raises ValueError. Enforces "overlay files must use
                         bare filenames" for v1 overlays.
    """
    linked = []
    for fname in list_dotfiles(source_dir, exclude=exclude_files):
        file_os = is_os_specific(fname)
        file_profile = is_profile_specific(fname)

        if reject_variants and (file_os or file_profile):
            kind = 'OS' if file_os else 'profile'
            raise ValueError(
                f'Overlay file {fname!r} has a {kind} prefix; overlay files '
                "must use bare filenames (the overlay's declared profile is "
                'applied at link time). Remove the prefix and rerun bootstrap. '
                '(OS variants inside an overlay are not supported in v1.)'
            )

        if file_os and file_os != os_type:
            continue
        if file_profile and file_profile != profile:
            continue
        linked.append(fname)

        target_name = fname
        if rename_prefix:
            # '.gitconfig' + prefix '.work' → '.work.gitconfig'
            # Strip one leading dot from fname so we don't get '..work.gitconfig'.
            stripped = fname[1:] if fname.startswith('.') else fname
            target_name = f'{rename_prefix}.{stripped}'

        _apply_link(
            os.path.join(home_dir, target_name),
            os.path.join(source_dir, fname),
            phase,
            dry_run,
            results,
        )
    return linked


def _link_variant_directory(
    variant_dir, home_dir, phase, exclude_files, forbid_names, dry_run, results
):
    """Link every file in a __os__/__profile__ dir to home_dir.

    Raises ValueError if any filename is in forbid_names (which is the set of
    root-level common dotfiles — a file can't be both common and OS-specific).
    """
    for fname in list_dotfiles(variant_dir, exclude=exclude_files):
        if fname in forbid_names:
            raise ValueError(f'conflict between {phase}-specific and common dotfiles: {fname}')
        _apply_link(
            os.path.join(home_dir, fname),
            os.path.join(variant_dir, fname),
            phase,
            dry_run,
            results,
        )


def _process_registry(source_dir, phase, os_type, profile, dry_run, results, already_processed):
    """Link every registry entry from source_dir/__registry__.yaml.

    Skips entries whose `abs_link` is already in `already_processed` — this is
    how overlay registry calls avoid re-linking paths the main registry owned.
    Returns the set of abs_link values this call processed so the caller can
    chain invocations.
    """
    reg_path = os.path.join(source_dir, REGISTRY_FILENAME)
    if not os.path.exists(reg_path):
        return set()

    processed = set()
    try:
        data = reg.load(reg_path)
    except (reg.RegistryError, yaml.YAMLError, KeyError) as e:
        LOG.error(f'Error reading {phase} registry: {e}')
        if phase == 'registered':
            LOG.error('Skipping registered files')
        return processed

    for entry in data.get('registered_files', []):
        entry_os = entry.get('os')
        entry_profile = entry.get('profile')
        if entry_os and entry_os != os_type:
            continue
        if entry_profile and entry_profile != profile:
            continue

        abs_real = os.path.join(source_dir, entry['repo_path'])
        abs_link = os.path.expanduser(entry['source_path'])

        if abs_link in already_processed:
            LOG.warning(
                f'{phase.capitalize()} entry {entry.get("id", "?")} duplicates '
                f'earlier source_path: {entry["source_path"]} (skipping)'
            )
            continue

        if not os.path.exists(abs_real):
            LOG.warning(
                f'{phase.capitalize()} entry {entry.get("id", "?")} points to '
                f'missing: {entry["repo_path"]}'
            )
            results.append(('missing', abs_link, abs_real, phase))
            continue

        _apply_link(abs_link, abs_real, phase, dry_run, results)
        processed.add(abs_link)

    return processed


def _collect_overlay_variants(overlay_dir, overlay_profile, exclude_files):
    """Treat bare overlay files as implicit profile-variants for the .local hub.

    Overlay files are named bare (`.zprofile`, not `.work.zprofile`); bootstrap
    renames them to `.<profile>.<basename>` at link time. For the .local hub
    to include those files, we need to register them as variants of the base
    dotfile under the overlay's declared profile.

    For each bare `.foo` in the overlay root, emit `{'.foo': ['.<profile>.foo']}`.
    The same `_link_root_dotfiles` rejection logic catches .os./.profile.
    prefixed filenames before they reach here, so every file we see is bare.

    Returns a dict of {base_dotfile: [profile_prefixed_variant_filename]}.
    """
    overlay_variants = {}
    for fname in list_dotfiles(overlay_dir, exclude=exclude_files):
        # list_dotfiles returns files, but bootstrap's overlay phase will
        # reject any prefixed filenames before _generate_local_files runs.
        # Here we just build the variant map; we can assume bare filenames.
        if not fname.startswith('.'):
            continue
        base = fname  # e.g. '.zprofile'
        profile_variant = f'.{overlay_profile}.{fname[1:]}'  # '.work.zprofile'
        overlay_variants[base] = [profile_variant]
    return overlay_variants


def _collect_variants(dotfiles_dir, overlay_dir, os_type, profile, exclude_files=None):
    """Merge OS/profile variants from main + overlay, deduping by filename.

    Main-repo variants come from `find_variant_files` (scans for `.<os>.<base>`
    and `.<profile>.<base>` patterns). Overlay variants come from the bare
    filenames in the overlay — each is a variant of its base under the
    overlay's declared profile.
    """
    variants = find_variant_files(dotfiles_dir, os_type, profile)
    if overlay_dir and os.path.isdir(overlay_dir):
        try:
            overlay_profile = _read_overlay_profile(overlay_dir)
        except reg.RegistryError:
            # If the overlay is malformed we'd have errored earlier in Phase 5.
            # Fall through silently here; _link_root_dotfiles would have
            # raised before reaching the .local phase in practice.
            return variants
        overlay_variants = _collect_overlay_variants(
            overlay_dir, overlay_profile, exclude_files or []
        )
        for base, vlist in overlay_variants.items():
            variants[base] = list(dict.fromkeys(variants.get(base, []) + vlist))
    return variants


def _generate_local_files(home_dir, all_variants, dry_run, results):
    """Write ~/<base>.local for each base dotfile that has OS/profile variants."""
    for base_dotfile, variant_list in sorted(all_variants.items()):
        local_name = f'{base_dotfile}.local'
        local_path = os.path.join(home_dir, local_name)
        contents = build_local_contents(base_dotfile, variant_list)

        try:
            if os.path.exists(local_path) or os.path.islink(local_path):
                if os.path.islink(local_path) and not os.path.exists(local_path):
                    if not dry_run:
                        os.unlink(local_path)
                else:
                    with open(local_path, 'r') as f:
                        existing = f.read()
                    if existing == contents:
                        results.append(('ok', local_path, None, 'local'))
                        continue
                action = 'would_update' if dry_run else 'updated'
            else:
                action = 'would_create' if dry_run else 'created'

            if not dry_run:
                import tempfile as _tempfile

                with _tempfile.NamedTemporaryFile(
                    'w', delete=False, dir=home_dir, prefix='.local-'
                ) as f:
                    f.write(contents)
                    temp_path = f.name
                os.replace(temp_path, local_path)

            results.append((action, local_path, None, 'local'))
        except OSError as e:
            LOG.warning(f'Could not write {local_name}: {e}')
            results.append(('error', local_path, None, 'local'))


def bootstrap(
    dotfiles_dir,
    home_dir,
    os_type,
    profile=None,
    skip_registry=False,
    dry_run=False,
    overlay_dir=None,
):
    """Bootstrap dotfiles by creating symlinks and generating .local files.

    Creates symlinks for common dotfiles, OS/profile variant files (filtered
    by active OS/profile), and registered files. Generates .local override
    files for dotfiles with variants. In dry_run mode, reports what would
    happen without making changes.

    If overlay_dir is provided, it is scanned as an additional layer after
    the main dotfiles_dir. Overlay entries override main entries on conflict.

    Returns a list of (action, link_path, target_path, phase) tuples where
    action is 'created', 'ok', 'repaired', 'updated', 'would_create',
    'would_update', 'would_repair', 'missing', or 'error'.
    target_path is None for .local file entries (phase='local').
    """
    assert os_type, 'os_type is required'
    results = []
    exclude_files = _compose_exclude_files(dotfiles_dir, overlay_dir)

    if not dry_run:
        _write_dotfiles_env(home_dir, os_type, profile, overlay_dir)

    # Phase 1: root-level common dotfiles (plus matching variants)
    common = _link_root_dotfiles(
        dotfiles_dir,
        home_dir,
        'common',
        os_type,
        profile,
        exclude_files,
        dry_run,
        results,
    )
    common_set = set(common)

    # Phase 2: __<os>__/ directory
    _link_variant_directory(
        os.path.join(dotfiles_dir, f'__{os_type}__'),
        home_dir,
        os_type,
        exclude_files,
        common_set,
        dry_run,
        results,
    )

    # Phase 3: __<profile>__/ directory
    if profile:
        _link_variant_directory(
            os.path.join(dotfiles_dir, f'__{profile}__'),
            home_dir,
            profile,
            exclude_files,
            common_set,
            dry_run,
            results,
        )

    # Phase 4: main registry
    processed = set()
    if not skip_registry:
        processed = _process_registry(
            dotfiles_dir,
            'registered',
            os_type,
            profile,
            dry_run,
            results,
            processed,
        )

    # Phase 5: overlay — root dotfiles + registry, deduped against main.
    # Under the "overlay = one implicit profile" model, overlay files are bare
    # (no profile prefix); bootstrap renames them to `.<profile>.<basename>` at
    # link time so they flow through the existing `.local` hub.
    if overlay_dir and os.path.isdir(overlay_dir):
        overlay_profile = _read_overlay_profile(overlay_dir)
        rename_prefix = f'.{overlay_profile}'
        _link_root_dotfiles(
            overlay_dir,
            home_dir,
            'overlay',
            os_type,
            overlay_profile,
            exclude_files,
            dry_run,
            results,
            rename_prefix=rename_prefix,
            reject_variants=True,
        )
        if not skip_registry:
            _process_registry(
                overlay_dir,
                'overlay',
                os_type,
                overlay_profile,
                dry_run,
                results,
                processed,
            )

    # Phase 6: .local generation
    all_variants = _collect_variants(
        dotfiles_dir, overlay_dir, os_type, profile, exclude_files=exclude_files
    )
    _generate_local_files(home_dir, all_variants, dry_run, results)

    return results


def find_symlink_dirs(home_dir, registry_data):
    """Find all directories where bootstrap might have created symlinks.

    Returns a set of absolute directory paths: the home directory plus
    the parent directory of each registered file's source_path.
    """
    dirs = {home_dir}
    for entry in registry_data.get('registered_files', []):
        source = os.path.expanduser(entry['source_path'])
        parent = os.path.dirname(source)
        if os.path.isdir(parent):
            dirs.add(parent)
    return dirs


def find_stale_symlinks(directories):
    """Find broken symlinks in the given directories (non-recursive).

    Returns list of (symlink_path, dead_target) tuples for symlinks
    whose targets no longer exist.
    """
    stale = []
    for directory in sorted(directories):
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            full_path = os.path.join(directory, name)
            if os.path.islink(full_path) and not os.path.exists(full_path):
                dead_target = os.readlink(full_path)
                stale.append((full_path, dead_target))
    return stale


def find_variant_files(dotfiles_dir, os_type, profile=None):
    """Find all OS/profile variant files and group by base dotfile.

    Scans repo root for files matching .<os>.X or .<profile>.X patterns.
    Returns a dict: {base_dotfile: [variant_filenames]}.
    E.g. {'.zprofile': ['.macos.zprofile', '.work.zprofile']}
    """
    variants = {}
    if not os.path.isdir(dotfiles_dir):
        return variants

    for fname in sorted(os.listdir(dotfiles_dir)):
        full_path = os.path.join(dotfiles_dir, fname)
        if not os.path.isfile(full_path):
            continue

        matched_os = is_os_specific(fname)
        matched_profile = is_profile_specific(fname)

        if matched_os and matched_os == os_type:
            # .macos.zprofile -> base is .zprofile
            base = fname[len(f'.{matched_os}.') :]
            if not base.startswith('.'):
                base = '.' + base
            variants.setdefault(base, []).append(fname)
        elif matched_profile and matched_profile == profile:
            # .work.gitconfig -> base is .gitconfig
            base = fname[len(f'.{matched_profile}.') :]
            if not base.startswith('.'):
                base = '.' + base
            variants.setdefault(base, []).append(fname)

    return variants


def build_local_contents(base_dotfile, variant_list):
    """Build the expected contents of a .local file for a given base dotfile."""
    tool_type = LOCAL_TOOL_TYPES.get(base_dotfile, 'shell')
    lines = ['# Auto-generated by dotfile bootstrap. Do not edit.']
    for variant in sorted(variant_list):
        lines.append(format_local_include(tool_type, variant))
    return '\n'.join(lines) + '\n'


def generate_local_files(dotfiles_dir, home_dir, os_type, profile=None, dry_run=False):
    """Generate .local files for dotfiles that have OS/profile variants.

    Returns a list of (action, local_path, contents) tuples.
    action is 'created', 'updated', 'ok', 'would_create', 'would_update',
    or 'error'.
    """
    variants = find_variant_files(dotfiles_dir, os_type, profile)
    results = []

    for base_dotfile, variant_list in sorted(variants.items()):
        local_name = f'{base_dotfile}.local'
        local_path = os.path.join(home_dir, local_name)
        contents = build_local_contents(base_dotfile, variant_list)

        try:
            if os.path.exists(local_path) or os.path.islink(local_path):
                # Remove dangling symlinks before reading
                if os.path.islink(local_path) and not os.path.exists(local_path):
                    if not dry_run:
                        os.unlink(local_path)
                else:
                    with open(local_path, 'r') as f:
                        existing = f.read()
                    if existing == contents:
                        results.append(('ok', local_path, contents))
                        continue
                action = 'would_update' if dry_run else 'updated'
            else:
                action = 'would_create' if dry_run else 'created'

            if not dry_run:
                # Atomic write: temp file + rename
                import tempfile

                with tempfile.NamedTemporaryFile(
                    'w', delete=False, dir=home_dir, prefix='.local-'
                ) as f:
                    f.write(contents)
                    temp_path = f.name
                os.replace(temp_path, local_path)

            results.append((action, local_path, contents))
        except OSError as e:
            LOG.warning(f'Could not write {local_name}: {e}')
            results.append(('error', local_path, ''))

    return results


def get_local_status(dotfiles_dir, home_dir, os_type, profile=None):
    """Get detailed .local file status for dotfiles with OS/profile variants.

    Returns a list of dicts, one per specialized dotfile:
    {
        'dotfile': '.zprofile',
        'local_name': '.zprofile.local',
        'local_exists': True,
        'local_fresh': True,
        'base_includes_local': True,
        'variants': [('.macos.zprofile', True), ('.work.zprofile', True)],
        'issues': [],
    }
    """
    results = []
    variants = find_variant_files(dotfiles_dir, os_type, profile)

    for base_dotfile, variant_list in sorted(variants.items()):
        local_name = f'{base_dotfile}.local'
        local_path = os.path.join(home_dir, local_name)
        base_path = os.path.join(home_dir, base_dotfile)

        info = {
            'dotfile': base_dotfile,
            'local_name': local_name,
            'local_exists': os.path.exists(local_path),
            'local_fresh': False,
            'base_includes_local': False,
            'variants': [],
            'issues': [],
        }

        # Check variants are symlinked into home
        for variant in sorted(variant_list):
            variant_home = os.path.join(home_dir, variant)
            linked = os.path.islink(variant_home)
            info['variants'].append((variant, linked))

        if not info['local_exists']:
            info['issues'].append(f'{local_name} missing')
        else:
            # Check freshness
            expected = build_local_contents(base_dotfile, variant_list)
            try:
                with open(local_path, 'r') as f:
                    actual = f.read()
                info['local_fresh'] = actual == expected
                if not info['local_fresh']:
                    info['issues'].append(f'{local_name} stale')
            except (OSError, UnicodeDecodeError):
                info['issues'].append(f'{local_name} unreadable')

        # Check base includes .local
        if os.path.exists(base_path) or os.path.islink(base_path):
            try:
                with open(base_path, 'r') as f:
                    base_contents = f.read()
                info['base_includes_local'] = local_name in base_contents
                if not info['base_includes_local']:
                    info['issues'].append(f'{base_dotfile} missing include')
            except (OSError, UnicodeDecodeError):
                pass

        results.append(info)

    return results


def check_local_health(dotfiles_dir, home_dir, os_type, profile=None):
    """Verify .local file health for dotfiles with OS/profile variants.

    Returns a list of (dotfile, issue_description) tuples for any problems found.
    """
    issues = []
    variants = find_variant_files(dotfiles_dir, os_type, profile)

    for base_dotfile, variant_list in sorted(variants.items()):
        local_name = f'{base_dotfile}.local'
        local_path = os.path.join(home_dir, local_name)
        base_path = os.path.join(home_dir, base_dotfile)

        # Check 1: .local file exists
        if not os.path.exists(local_path):
            issues.append(
                (base_dotfile, f'{local_name} missing — run `dotfile bootstrap` to generate')
            )
            continue

        # Check 2: .local contents match current OS/profile
        expected = build_local_contents(base_dotfile, variant_list)

        try:
            with open(local_path, 'r') as f:
                actual = f.read()
        except (OSError, UnicodeDecodeError) as e:
            issues.append((base_dotfile, f'cannot read {local_name}: {e}'))
            continue

        if actual != expected:
            issues.append(
                (base_dotfile, f'{local_name} is stale — run `dotfile bootstrap` to refresh')
            )
            continue  # stale .local may reference old variants; skip checks 3-4

        # Check 3: main dotfile includes .local
        if os.path.exists(base_path) or os.path.islink(base_path):
            try:
                with open(base_path, 'r') as f:
                    base_contents = f.read()
                if local_name not in base_contents:
                    issues.append((base_dotfile, f'{base_dotfile} does not include {local_name}'))
            except (OSError, UnicodeDecodeError):
                pass  # binary file or unreadable — skip

        # Check 4: variant files referenced in .local exist
        for variant in variant_list:
            variant_path = os.path.join(dotfiles_dir, variant)
            if not os.path.isfile(variant_path):
                issues.append((base_dotfile, f'variant {variant} referenced but missing from repo'))

    return issues
