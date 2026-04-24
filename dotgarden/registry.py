"""Registry CRUD operations for dotfiles management."""

import json
import os
import re
import tempfile

import yaml

from dotgarden.config import DEFAULT_OS_NAMES


class RegistryError(Exception):
    """Raised when registry operations fail."""


# Top-level keys that are metadata, not category entry lists.
# `profile` is the overlay-scope declaration ("this entire registry applies to
# profile: <name>"); only overlay registries set it — main repo registries
# leave it unset.
METADATA_KEYS = {'version', 'os', 'profiles', 'ignore_files', 'ignore_dirs', 'profile'}

# Registry format versions this build of dotgarden can read. Any change to
# the on-disk format that isn't forward-compatible MUST add a new value here
# and bump the `version` field new registries write. See AGENTS.md "Registry
# format version" section for the discipline.
#   1.0 — legacy JSON format (pre-v2)
#   2.0 — verbose YAML, one full entry dict per item
#   3.0 — compact YAML, {repo_path: source_path} per item (current)
KNOWN_REGISTRY_VERSIONS = frozenset({'1.0', '2.0', '3.0'})


def _validate_version(version, registry_path):
    """Raise RegistryError if the version isn't one this build understands."""
    if version not in KNOWN_REGISTRY_VERSIONS:
        known = ', '.join(sorted(KNOWN_REGISTRY_VERSIONS))
        raise RegistryError(
            f'Unknown registry format version {version!r} in {registry_path}. '
            f'This dotgarden build knows: {known}. '
            'Upgrade dotgarden, or edit the registry to a supported version.'
        )


def get_overlay_profile(registry_data, registry_path):
    """Return the overlay's declared profile, raising if it's missing.

    Call this whenever bootstrap / register / etc. are about to act on a
    registry that came from an overlay directory. Overlays MUST declare
    their profile once at the top of `__registry__.yaml` (e.g. `profile: work`)
    — this helper is the single place that enforces it, so the error message
    is consistent across callers.

    Main-repo registries don't carry a `profile` field; don't call this on
    them.
    """
    profile = registry_data.get('profile')
    if not profile:
        raise RegistryError(
            f'Overlay registry {registry_path} is missing the required '
            '`profile: <name>` top-level field. Every overlay must declare '
            'which profile its contents apply to. Add a line like '
            '`profile: work` near the top of the file.'
        )
    return profile


# Extensions stripped from the tail of a derived ID. Common config formats
# whose name-minus-extension reads cleanly as a short identifier.
_ID_STRIP_EXTENSIONS = ('.json', '.yaml', '.yml', '.toml', '.kdl', '.fish',
                        '.conf', '.lua', '.sh')


def _strip_segment(segment):
    """Strip leading _ and . so each path segment contributes a clean token.

    The leading-dot strip is what keeps IDs readable — '.bashrc' becomes
    'bashrc', not '.bashrc', after segment-level normalization. Earlier
    versions did this only once at the start of the whole path, which
    broke IDs like `_uncategorized/.bashrc` (produced
    'uncategorized-.bashrc' instead of 'uncategorized-bashrc').
    """
    return segment.lstrip('_').lstrip('.')


def _strip_known_extension(name):
    for ext in _ID_STRIP_EXTENSIONS:
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def derive_id(repo_path):
    """Derive a stable ID from a repo path.

    Examples:
        _cursor/settings.json        -> cursor-settings
        _fish/config.fish            -> fish-config
        __macos__/sketchybar         -> sketchybar
        _nvim                        -> nvim
        _uncategorized/.bashrc       -> uncategorized-bashrc
        __macos__/.macos-thing       -> macos-thing
    """
    name = re.sub(r'^__[a-z]+__/', '', repo_path)
    segments = [_strip_segment(s) for s in name.split('/')]
    name = '-'.join(s for s in segments if s)
    return _strip_known_extension(name)


def derive_id_from_source(source_path):
    """Derive an ID from source path, for disambiguation when repo_path collides."""
    name = source_path.replace('~/', '')
    segments = [_strip_segment(s) for s in name.split('/')]
    name = '-'.join(s for s in segments if s)
    return _strip_known_extension(name)


def load(registry_path):
    """Load registry, returning a new empty registry if the file doesn't exist.

    Reads v3 (compact), v2 (verbose YAML), or legacy JSON (v1).
    Returns the standard in-memory format with full entry dicts.

    Raises RegistryError on corruption or invalid schema.
    """
    if not os.path.exists(registry_path):
        return {'version': '3.0', 'registered_files': []}

    try:
        with open(registry_path, 'r') as f:
            content = f.read()
    except OSError as e:
        raise RegistryError(f'Error reading registry {registry_path}: {e}')

    if registry_path.endswith('.yaml') or registry_path.endswith('.yml'):
        return _load_yaml(content, registry_path)
    else:
        return _load_json(content, registry_path)


def _load_yaml(content, registry_path):
    """Parse YAML registry into flat in-memory format.

    Handles v3 (compact: repo_path: source_path mappings),
    v2 (verbose: full entry dicts), or either transparently.
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise RegistryError(f'Error loading registry {registry_path}: {e}')

    if not isinstance(data, dict) or 'version' not in data:
        raise RegistryError(f'Invalid registry schema in {registry_path}')

    version = str(data['version'])
    _validate_version(version, registry_path)

    entries = []
    seen_ids = set()
    # Use registry-level OS metadata if available, else defaults
    os_names = data.get('os')

    for category, value in data.items():
        if category in METADATA_KEYS:
            continue

        if isinstance(value, list):
            for item in value:
                entry = _parse_entry(item, category, seen_ids, os_names=os_names)
                if entry:
                    entries.append(entry)
        elif isinstance(value, dict):
            # Conditional entries keyed by OS or profile name
            for condition_key, item_list in value.items():
                if not isinstance(item_list, list):
                    continue
                for item in item_list:
                    entry = _parse_entry(
                        item, category, seen_ids, condition_key=condition_key, os_names=os_names
                    )
                    if entry:
                        entries.append(entry)
        else:
            raise RegistryError(
                f'Invalid registry schema in {registry_path}: category {category!r} is not a list or dict'
            )

    result = {'version': version, 'registered_files': entries}
    if 'os' in data:
        result['os'] = data['os']
    if 'profiles' in data:
        result['profiles'] = data['profiles']
    if 'ignore_files' in data:
        result['ignore_files'] = list(data['ignore_files'] or [])
    if 'ignore_dirs' in data:
        result['ignore_dirs'] = list(data['ignore_dirs'] or [])
    if 'profile' in data:
        result['profile'] = data['profile']
    return result


def _parse_entry(item, category, seen_ids, condition_key=None, os_names=None):
    """Parse a single registry entry from either v2 or v3 format."""
    if isinstance(item, dict) and len(item) == 1 and 'id' not in item:
        # v3 compact: {repo_path: source_path}
        repo_path, source_path = next(iter(item.items()))
        return _build_entry(repo_path, source_path, category, seen_ids, condition_key, os_names)
    elif isinstance(item, dict) and 'repo_path' in item:
        # v2 verbose: full entry dict with all fields
        # Ensure id is populated
        if 'id' not in item:
            entry_id = derive_id(item['repo_path'])
            if entry_id in seen_ids:
                entry_id = derive_id_from_source(item['source_path'])
            seen_ids.add(entry_id)
            item['id'] = entry_id
        else:
            seen_ids.add(item['id'])
        if 'category' not in item:
            item['category'] = category
        return item
    return None


def _build_entry(repo_path, source_path, category, seen_ids, condition_key=None, os_names=None):
    """Build a full entry dict from compact v3 data."""
    entry_id = derive_id(repo_path)
    if entry_id in seen_ids:
        entry_id = derive_id_from_source(source_path)
        if entry_id in seen_ids:
            # Third-level collision — append counter
            base = entry_id
            counter = 2
            while entry_id in seen_ids:
                entry_id = f'{base}-{counter}'
                counter += 1
    seen_ids.add(entry_id)

    if os_names is None:
        os_names = DEFAULT_OS_NAMES

    entry = {
        'id': entry_id,
        'source_path': source_path,
        'repo_path': repo_path,
        'category': category,
        'os': None,
        'profile': None,
    }

    # 'all' is the sentinel for unconditional entries in mixed categories
    if condition_key and condition_key != 'all':
        if condition_key in os_names:
            entry['os'] = condition_key
        else:
            entry['profile'] = condition_key

    return entry


def _load_json(content, registry_path):
    """Parse legacy JSON registry."""
    try:
        registry = json.loads(content)
    except json.JSONDecodeError as e:
        raise RegistryError(f'Error loading registry {registry_path}: {e}')
    if 'version' not in registry or 'registered_files' not in registry:
        raise RegistryError(f'Invalid registry schema in {registry_path}')
    _validate_version(str(registry['version']), registry_path)
    return registry


def save(registry, registry_path, dotfiles_dir=None):
    """Save registry as compact v3 YAML.

    dotfiles_dir is used as the directory for the temp file.
    If not provided, uses the parent directory of registry_path.
    """
    if dotfiles_dir is None:
        dotfiles_dir = os.path.dirname(registry_path)

    output = {'version': '3.0'}
    if 'profile' in registry:
        # Overlay scope declaration — render early for visibility at the top
        # of the file.
        output['profile'] = registry['profile']
    if 'os' in registry:
        output['os'] = registry['os']
    if 'profiles' in registry:
        output['profiles'] = registry['profiles']
    if registry.get('ignore_files'):
        output['ignore_files'] = list(registry['ignore_files'])
    if registry.get('ignore_dirs'):
        output['ignore_dirs'] = list(registry['ignore_dirs'])

    # Group entries by category, then by condition
    categories = {}
    for entry in registry['registered_files']:
        cat = entry.get('category') or 'uncategorized'
        categories.setdefault(cat, []).append(entry)

    for cat in sorted(categories):
        cat_entries = categories[cat]
        has_conditions = any(e.get('os') or e.get('profile') for e in cat_entries)

        def _compact(e):
            rp = e.get('repo_path', e.get('id', ''))
            sp = e.get('source_path', '')
            return {rp: sp}

        if not has_conditions:
            output[cat] = [_compact(e) for e in cat_entries]
        else:
            groups = {}
            for e in cat_entries:
                condition = e.get('os') or e.get('profile')
                if condition:
                    groups.setdefault(condition, []).append(_compact(e))
                else:
                    groups.setdefault('all', []).append(_compact(e))
            output[cat] = {k: groups[k] for k in sorted(groups)}

    with tempfile.NamedTemporaryFile('w', delete=False, dir=dotfiles_dir) as f:
        yaml.safe_dump(output, f, default_flow_style=False, sort_keys=False)
        temp_path = f.name

    os.replace(temp_path, registry_path)


def find_by_id(registry, entry_id):
    """Find registry entry by ID. Returns entry dict or None."""
    for entry in registry['registered_files']:
        if entry.get('id') == entry_id:
            return entry
        repo_path = entry.get('repo_path')
        if repo_path and derive_id(repo_path) == entry_id:
            return entry
    return None


def find_by_source(registry, source_path):
    """Find registry entry by source path. Returns entry dict or None."""
    for entry in registry['registered_files']:
        if entry['source_path'] == source_path:
            return entry
    return None


def find_by_repo_path(registry, repo_path):
    """Find registry entry by repo path. Returns entry dict or None."""
    for entry in registry['registered_files']:
        if entry['repo_path'] == repo_path:
            return entry
    return None


def find_all_by_repo_path(registry, repo_path):
    """Find all registry entries sharing the same repo path.

    Multiple entries can point to the same repo file (e.g. a skill shared
    between ~/.claude/skills/ and ~/.codex/skills/). Returns a list of
    entry dicts (may be empty).
    """
    return [e for e in registry['registered_files'] if e['repo_path'] == repo_path]


def add(registry, entry):
    """Add entry to registry."""
    registry['registered_files'].append(entry)


def remove(registry, entry_id):
    """Remove entry from registry by ID. Removes the first match only."""
    entries = registry['registered_files']
    # Try stored id first, then derive_id fallback
    for i, e in enumerate(entries):
        if e.get('id') == entry_id:
            entries.pop(i)
            return
    for i, e in enumerate(entries):
        if e.get('repo_path') and derive_id(e['repo_path']) == entry_id:
            entries.pop(i)
            return
