"""Tests for lib.registry module."""

import os
import shutil
import tempfile
import unittest

import pytest
import yaml

from dotgarden.registry import (
    RegistryError,
    add,
    derive_id,
    find_by_id,
    find_by_repo_path,
    find_by_source,
    get_overlay_profile,
    load,
    remove,
    save,
)


class TestDeriveId(unittest.TestCase):
    def test_standard_cases(self):
        cases = [
            ('_cursor/settings.json', 'cursor-settings'),
            ('_fish/config.fish', 'fish-config'),
            ('_fish/completions', 'fish-completions'),
            ('_nvim', 'nvim'),
            ('_myapp/init.sh', 'myapp-init'),
            ('__macos__/sketchybar', 'sketchybar'),
            ('_zellij/config.kdl', 'zellij-config'),
        ]
        for repo_path, expected in cases:
            with self.subTest(repo_path=repo_path):
                assert derive_id(repo_path) == expected


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry_path = os.path.join(self.tmpdir, 'registry.yaml')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_returns_empty_registry_when_missing(self):
        result = load(self.registry_path)
        assert result['version'] == '3.0'
        assert result['registered_files'] == []

    def test_loads_v3_compact(self):
        content = """\
version: '3.0'
fish:
  - _fish/config.fish: ~/.config/fish/config.fish
  - _fish/completions: ~/.config/fish/completions
"""
        with open(self.registry_path, 'w') as f:
            f.write(content)

        result = load(self.registry_path)
        assert len(result['registered_files']) == 2
        assert result['registered_files'][0]['id'] == 'fish-config'
        assert result['registered_files'][0]['category'] == 'fish'
        assert result['registered_files'][0]['repo_path'] == '_fish/config.fish'

    def test_loads_v3_conditional(self):
        content = """\
version: '3.0'
cursor:
  macos:
    - _cursor/settings.json: ~/Library/Application Support/Cursor/User/settings.json
"""
        with open(self.registry_path, 'w') as f:
            f.write(content)

        result = load(self.registry_path)
        assert len(result['registered_files']) == 1
        entry = result['registered_files'][0]
        assert entry['os'] == 'macos'
        assert entry['category'] == 'cursor'

    def test_loads_v2_verbose(self):
        data = {
            'version': '2.0',
            'fish': [
                {
                    'id': 'fish-config',
                    'source_path': '~/.config/fish/config.fish',
                    'repo_path': '_fish/config.fish',
                    'category': 'fish',
                },
            ],
        }
        with open(self.registry_path, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        result = load(self.registry_path)
        assert len(result['registered_files']) == 1
        assert result['registered_files'][0]['id'] == 'fish-config'

    def test_loads_metadata(self):
        content = """\
version: '3.0'
os: [macos, linux]
profiles: [work, home]
fish:
  - _fish/config.fish: ~/.config/fish/config.fish
"""
        with open(self.registry_path, 'w') as f:
            f.write(content)

        result = load(self.registry_path)
        assert result['os'] == ['macos', 'linux']
        assert result['profiles'] == ['work', 'home']

    def test_raises_on_bad_registry(self):
        cases = [
            ('not: valid: yaml: [', 'invalid YAML'),
            (yaml.safe_dump({'fish': [{'id': 'test'}]}), 'missing version'),
        ]
        for content, desc in cases:
            with self.subTest(desc=desc):
                with open(self.registry_path, 'w') as f:
                    f.write(content)
                with self.assertRaises(RegistryError):
                    load(self.registry_path)

    def test_raises_on_invalid_category_type(self):
        data = {'version': '3.0', 'fish': 'not-a-list-or-dict'}
        with open(self.registry_path, 'w') as f:
            yaml.safe_dump(data, f)
        with self.assertRaises(RegistryError):
            load(self.registry_path)

    def test_raises_on_unknown_version(self):
        """Any version not in KNOWN_REGISTRY_VERSIONS must fail at load.

        This is the forward-incompatibility guard: if a newer dotgarden
        writes a registry with version 4.0, older dotgarden refuses to
        silently misread it. Documented in AGENTS.md under "Registry
        format version".
        """
        data = {'version': '99.0', 'fish': []}
        with open(self.registry_path, 'w') as f:
            yaml.safe_dump(data, f)
        with self.assertRaises(RegistryError) as ctx:
            load(self.registry_path)
        msg = str(ctx.exception)
        assert '99.0' in msg
        assert 'Upgrade dotgarden' in msg or 'edit the registry' in msg

    def test_accepts_known_versions(self):
        """Sanity: 1.0 (JSON), 2.0 (verbose YAML), 3.0 (compact YAML) all load."""
        import json

        # v3.0 (compact YAML) — already covered by test_loads_v3_compact above.
        # v2.0 (verbose YAML)
        v2_path = os.path.join(self.tmpdir, 'v2.yaml')
        with open(v2_path, 'w') as f:
            yaml.safe_dump({'version': '2.0', 'registered_files': []}, f)
        assert load(v2_path)['version'] == '2.0'

        # v1.0 (legacy JSON)
        v1_path = os.path.join(self.tmpdir, 'v1.json')
        with open(v1_path, 'w') as f:
            json.dump({'version': '1.0', 'registered_files': []}, f)
        assert load(v1_path)['version'] == '1.0'

    def test_disambiguates_duplicate_repo_paths(self):
        content = """\
version: '3.0'
skills:
  - _skills/spec-suite-qa: ~/.claude/skills/spec-suite-qa
  - _skills/spec-suite-qa: ~/.codex/skills/spec-suite-qa
"""
        with open(self.registry_path, 'w') as f:
            f.write(content)

        result = load(self.registry_path)
        ids = [e['id'] for e in result['registered_files']]
        assert len(set(ids)) == 2  # unique IDs
        assert 'skills-spec-suite-qa' in ids


class TestSave(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry_path = os.path.join(self.tmpdir, 'registry.yaml')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_saves_and_loads_roundtrip(self):
        data = {
            'version': '3.0',
            'registered_files': [
                {'id': 'foo', 'source_path': '~/.foo', 'repo_path': '.foo', 'category': 'misc'},
            ],
        }
        save(data, self.registry_path)
        loaded = load(self.registry_path)
        assert len(loaded['registered_files']) == 1
        assert loaded['registered_files'][0]['source_path'] == '~/.foo'
        assert loaded['registered_files'][0]['repo_path'] == '.foo'
        assert loaded['registered_files'][0]['category'] == 'misc'

    def test_overwrites_existing(self):
        save(
            {
                'version': '3.0',
                'registered_files': [
                    {'repo_path': 'a', 'source_path': '~/a', 'category': 'test'},
                ],
            },
            self.registry_path,
        )
        save(
            {
                'version': '3.0',
                'registered_files': [
                    {'repo_path': 'b', 'source_path': '~/b', 'category': 'test'},
                ],
            },
            self.registry_path,
        )
        assert len(load(self.registry_path)['registered_files']) == 1

    def test_compact_format_on_disk(self):
        data = {
            'version': '3.0',
            'registered_files': [
                {
                    'repo_path': '_fish/config.fish',
                    'source_path': '~/.config/fish/config.fish',
                    'category': 'fish',
                },
                {
                    'repo_path': '_cursor/settings.json',
                    'source_path': '~/cursor/settings.json',
                    'category': 'cursor',
                    'os': 'macos',
                },
            ],
        }
        save(data, self.registry_path)

        with open(self.registry_path) as f:
            raw = yaml.safe_load(f)

        assert raw['version'] == '3.0'
        assert 'fish' in raw
        assert 'cursor' in raw
        # v3: no id, category, registered_at in the YAML
        assert 'registered_files' not in raw
        # fish is unconditional — flat list
        assert isinstance(raw['fish'], list)
        # cursor is conditional — dict keyed by OS
        assert isinstance(raw['cursor'], dict)
        assert 'macos' in raw['cursor']

    def test_preserves_metadata(self):
        data = {
            'version': '3.0',
            'os': ['macos', 'linux'],
            'profiles': ['work', 'home'],
            'registered_files': [
                {
                    'repo_path': '_fish/config.fish',
                    'source_path': '~/.config/fish/config.fish',
                    'category': 'fish',
                },
            ],
        }
        save(data, self.registry_path)

        with open(self.registry_path) as f:
            raw = yaml.safe_load(f)
        assert raw['os'] == ['macos', 'linux']
        assert raw['profiles'] == ['work', 'home']

    def test_uncategorized_entries(self):
        data = {
            'version': '3.0',
            'registered_files': [
                {'repo_path': '.bashrc', 'source_path': '~/.bashrc', 'category': None},
            ],
        }
        save(data, self.registry_path)

        with open(self.registry_path) as f:
            raw = yaml.safe_load(f)
        assert 'uncategorized' in raw


# -- Table-driven: finders --

REGISTRY_FIXTURE = {
    'version': '3.0',
    'registered_files': [
        {
            'id': 'vscode-settings',
            'source_path': '~/Code/settings.json',
            'repo_path': '_vscode/settings.json',
        },
        {
            'id': 'zed-keymap',
            'source_path': '~/.config/zed/keymap.json',
            'repo_path': '_zed/keymap.json',
        },
    ],
}

FIND_BY_ID_CASES = [
    ('vscode-settings', 'vscode-settings'),
    ('zed-keymap', 'zed-keymap'),
    ('nonexistent', None),
]


@pytest.mark.parametrize(
    'query,expected_id', FIND_BY_ID_CASES, ids=[c[0] for c in FIND_BY_ID_CASES]
)
def test_find_by_id(query, expected_id):
    entry = find_by_id(REGISTRY_FIXTURE, query)
    assert (entry['id'] if entry else None) == expected_id


FIND_BY_SOURCE_CASES = [
    ('~/Code/settings.json', 'vscode-settings'),
    ('~/.config/zed/keymap.json', 'zed-keymap'),
    ('~/nonexistent', None),
]


@pytest.mark.parametrize(
    'query,expected_id', FIND_BY_SOURCE_CASES, ids=[c[0] for c in FIND_BY_SOURCE_CASES]
)
def test_find_by_source(query, expected_id):
    entry = find_by_source(REGISTRY_FIXTURE, query)
    assert (entry['id'] if entry else None) == expected_id


FIND_BY_REPO_PATH_CASES = [
    ('_vscode/settings.json', 'vscode-settings'),
    ('_zed/keymap.json', 'zed-keymap'),
    ('nonexistent/path', None),
]


@pytest.mark.parametrize(
    'query,expected_id', FIND_BY_REPO_PATH_CASES, ids=[c[0] for c in FIND_BY_REPO_PATH_CASES]
)
def test_find_by_repo_path(query, expected_id):
    entry = find_by_repo_path(REGISTRY_FIXTURE, query)
    assert (entry['id'] if entry else None) == expected_id


def test_find_by_derived_id():
    """find_by_id should match derived IDs even if entry has no stored id."""
    registry = {
        'version': '3.0',
        'registered_files': [
            {'repo_path': '_cursor/settings.json', 'source_path': '~/cursor/settings.json'},
        ],
    }
    entry = find_by_id(registry, 'cursor-settings')
    assert entry is not None
    assert entry['repo_path'] == '_cursor/settings.json'


# -- Add/remove --


def test_add():
    registry = {'version': '3.0', 'registered_files': []}
    add(registry, {'id': 'new-entry', 'repo_path': '.new', 'source_path': '~/.new'})
    assert len(registry['registered_files']) == 1


def test_remove():
    registry = {
        'version': '3.0',
        'registered_files': [
            {'id': 'keep', 'repo_path': '.keep', 'source_path': '~/.keep'},
            {'id': 'delete', 'repo_path': '.delete', 'source_path': '~/.delete'},
        ],
    }
    remove(registry, 'delete')
    assert len(registry['registered_files']) == 1
    assert registry['registered_files'][0]['id'] == 'keep'


def test_remove_nonexistent_is_noop():
    registry = {
        'version': '3.0',
        'registered_files': [{'id': 'keep', 'repo_path': '.keep', 'source_path': '~/.keep'}],
    }
    remove(registry, 'nonexistent')
    assert len(registry['registered_files']) == 1


class TestDeriveIdEdgeCases(unittest.TestCase):
    def test_bare_dotfiles(self):
        assert derive_id('.vimrc') == 'vimrc'
        assert derive_id('.bashrc') == 'bashrc'

    def test_linux_prefix(self):
        assert derive_id('__linux__/something') == 'something'

    def test_multi_dot_extension(self):
        # .tmux.conf ends with .conf which is in the extension list
        assert derive_id('.tmux.conf') == 'tmux'

    def test_conf_d_directory(self):
        assert derive_id('_fish/conf.d') == 'fish-conf.d'


class TestRoundtrip(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry_path = os.path.join(self.tmpdir, 'registry.yaml')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_os_condition_roundtrip(self):
        data = {
            'version': '3.0',
            'registered_files': [
                {
                    'repo_path': '_cursor/settings.json',
                    'source_path': '~/Library/Application Support/Cursor/User/settings.json',
                    'category': 'cursor',
                    'os': 'macos',
                    'profile': None,
                },
            ],
        }
        save(data, self.registry_path)
        loaded = load(self.registry_path)
        entry = loaded['registered_files'][0]
        assert entry['os'] == 'macos'
        assert entry['profile'] is None
        assert entry['category'] == 'cursor'

    def test_profile_condition_roundtrip(self):
        data = {
            'version': '3.0',
            'profiles': ['work', 'home'],
            'registered_files': [
                {
                    'repo_path': '_private/work-config',
                    'source_path': '~/.work-config',
                    'category': 'private',
                    'os': None,
                    'profile': 'work',
                },
            ],
        }
        save(data, self.registry_path)
        loaded = load(self.registry_path)
        entry = loaded['registered_files'][0]
        assert entry['profile'] == 'work'
        assert entry['os'] is None

    def test_mixed_condition_category_roundtrip(self):
        """Category with both conditional and unconditional entries."""
        data = {
            'version': '3.0',
            'registered_files': [
                {
                    'repo_path': '_tools/common-tool',
                    'source_path': '~/.common-tool',
                    'category': 'tools',
                    'os': None,
                    'profile': None,
                },
                {
                    'repo_path': '_tools/mac-tool',
                    'source_path': '~/.mac-tool',
                    'category': 'tools',
                    'os': 'macos',
                    'profile': None,
                },
            ],
        }
        save(data, self.registry_path)
        loaded = load(self.registry_path)
        entries = loaded['registered_files']
        assert len(entries) == 2

        unconditional = [e for e in entries if e['repo_path'] == '_tools/common-tool'][0]
        conditional = [e for e in entries if e['repo_path'] == '_tools/mac-tool'][0]
        assert unconditional['os'] is None
        assert unconditional['profile'] is None
        assert conditional['os'] == 'macos'

    def test_v2_to_v3_migration_roundtrip(self):
        """Load v2, save as v3, load again — data preserved."""
        v2_content = {
            'version': '2.0',
            'fish': [
                {
                    'id': 'fish-config',
                    'source_path': '~/.config/fish/config.fish',
                    'repo_path': '_fish/config.fish',
                    'category': 'fish',
                    'os': None,
                    'profile': None,
                    'registered_at': '2026-01-01T00:00:00Z',
                },
            ],
        }
        with open(self.registry_path, 'w') as f:
            yaml.safe_dump(v2_content, f, default_flow_style=False, sort_keys=False)

        # Load v2
        loaded = load(self.registry_path)
        assert loaded['registered_files'][0]['repo_path'] == '_fish/config.fish'

        # Save as v3
        loaded['version'] = '3.0'
        save(loaded, self.registry_path)

        # Reload and verify
        reloaded = load(self.registry_path)
        entry = reloaded['registered_files'][0]
        assert entry['repo_path'] == '_fish/config.fish'
        assert entry['source_path'] == '~/.config/fish/config.fish'
        assert entry['category'] == 'fish'

    def test_metadata_roundtrip(self):
        data = {
            'version': '3.0',
            'os': ['macos', 'linux', 'windows'],
            'profiles': ['work', 'home'],
            'registered_files': [
                {
                    'repo_path': '_fish/config.fish',
                    'source_path': '~/.config/fish/config.fish',
                    'category': 'fish',
                },
            ],
        }
        save(data, self.registry_path)
        loaded = load(self.registry_path)
        assert loaded['os'] == ['macos', 'linux', 'windows']
        assert loaded['profiles'] == ['work', 'home']

    def test_custom_os_in_metadata(self):
        """Custom OS name in metadata should be recognized as OS, not profile."""
        content = """\
version: '3.0'
os: [macos, linux, windows]
myapp:
  windows:
    - _myapp/config: ~/.myapp/config
"""
        with open(self.registry_path, 'w') as f:
            f.write(content)

        loaded = load(self.registry_path)
        entry = loaded['registered_files'][0]
        assert entry['os'] == 'windows'
        assert entry['profile'] is None

    def test_profile_metadata_roundtrip(self):
        """Overlay registries declare their scope via top-level `profile:`.
        Ensure it survives load → save → load unchanged, and doesn't
        accidentally parse as a category name."""
        data = {
            'version': '3.0',
            'profile': 'work',
            'registered_files': [
                {
                    'repo_path': '_myapp/init.sh',
                    'source_path': '~/.myapp/profile/init.sh',
                    'category': 'myapp',
                },
            ],
        }
        save(data, self.registry_path)
        loaded = load(self.registry_path)
        assert loaded['profile'] == 'work'
        assert len(loaded['registered_files']) == 1
        assert loaded['registered_files'][0]['category'] == 'myapp'

    def test_profile_metadata_not_treated_as_category(self):
        """`profile: work` at top level must NOT create a phantom category
        named `profile` with value `work`."""
        content = """\
version: '3.0'
profile: work
myapp:
  - _myapp/init.sh: ~/.myapp/profile/init.sh
"""
        with open(self.registry_path, 'w') as f:
            f.write(content)

        loaded = load(self.registry_path)
        categories = {e['category'] for e in loaded['registered_files']}
        assert 'profile' not in categories
        assert categories == {'myapp'}


class TestFindByIdEdgeCases(unittest.TestCase):
    def test_entry_without_repo_path(self):
        """find_by_id should not crash on entries missing repo_path."""
        registry = {
            'version': '3.0',
            'registered_files': [
                {'id': 'manual-entry', 'source_path': '~/.something'},
            ],
        }
        # Should find by stored id
        assert find_by_id(registry, 'manual-entry') is not None
        # Should not crash when trying derive_id
        assert find_by_id(registry, 'nonexistent') is None


class TestGetOverlayProfile(unittest.TestCase):
    """get_overlay_profile enforces that overlay registries declare their scope.

    See AGENTS.md "Registry format version" + the 2026-04-20 strategy update
    (decision 4) in the pip-package plan for why this is required.
    """

    def test_returns_profile_when_declared(self):
        data = {'version': '3.0', 'profile': 'work', 'registered_files': []}
        assert get_overlay_profile(data, '/fake/overlay/__registry__.yaml') == 'work'

    def test_raises_when_profile_missing(self):
        data = {'version': '3.0', 'registered_files': []}
        with pytest.raises(RegistryError) as exc_info:
            get_overlay_profile(data, '/fake/overlay/__registry__.yaml')
        msg = str(exc_info.value)
        assert 'missing' in msg.lower()
        assert 'profile' in msg
        assert '/fake/overlay/__registry__.yaml' in msg

    def test_raises_when_profile_empty_string(self):
        """An empty-string profile is as good as missing — reject."""
        data = {'version': '3.0', 'profile': '', 'registered_files': []}
        with pytest.raises(RegistryError):
            get_overlay_profile(data, '/fake/path.yaml')

    def test_raises_when_profile_none(self):
        data = {'version': '3.0', 'profile': None, 'registered_files': []}
        with pytest.raises(RegistryError):
            get_overlay_profile(data, '/fake/path.yaml')


if __name__ == '__main__':
    unittest.main()
