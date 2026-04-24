"""Tests for lib.symlinks module."""

import shutil
import tempfile
import unittest
from os import makedirs, readlink, remove, symlink, unlink  # noqa: TID251
from os.path import exists, isdir, islink, join, realpath  # noqa: TID251

import pytest

from dotgarden.symlinks import (
    bootstrap,
    check_status,
    create_symlink,
    discover_bootstrap_managed,
    find_stale_symlinks,
    find_symlink_dirs,
    list_dot_config_children,
    list_dotfiles,
    prepare_symlink_target,
)


class TestListDotfiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _touch(self, *names):
        for name in names:
            open(join(self.tmpdir, name), 'w').close()

    def test_lists_files_sorted(self):
        self._touch('.zshrc', '.bashrc', '.aliases')
        assert list_dotfiles(self.tmpdir) == ['.aliases', '.bashrc', '.zshrc']

    def test_excludes_not_dotfiles(self):
        self._touch('.bashrc', 'README.md', '__registry__.yaml')
        assert list_dotfiles(self.tmpdir) == ['.bashrc']

    def test_excludes_md_files_by_extension(self):
        self._touch('.bashrc', 'AGENTS.md', 'CHANGELOG.md')
        assert list_dotfiles(self.tmpdir) == ['.bashrc']

    def test_skips_directories(self):
        self._touch('.bashrc')
        makedirs(join(self.tmpdir, 'subdir'))
        assert list_dotfiles(self.tmpdir) == ['.bashrc']

    def test_returns_empty_for_nonexistent(self):
        assert list_dotfiles('/nonexistent/dir') == []


class TestPrepareSymlinkTarget(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_needed_when_link_missing(self):
        target = join(self.tmpdir, 'target')
        open(target, 'w').close()
        assert prepare_symlink_target(target, join(self.tmpdir, 'link')) == 'needed'

    def test_ok_when_already_correct(self):
        target = join(self.tmpdir, 'target')
        link = join(self.tmpdir, 'link')
        open(target, 'w').close()
        symlink(target, link)
        assert prepare_symlink_target(target, link) == 'ok'

    def test_replaced_backs_up_conflicting_file(self):
        target = join(self.tmpdir, 'target')
        link = join(self.tmpdir, 'link')
        open(target, 'w').close()
        with open(link, 'w') as f:
            f.write('old')

        assert prepare_symlink_target(target, link) == 'replaced'
        assert not exists(link)
        assert exists(link + '.bak')

    def test_stale_removes_dead_symlink(self):
        target = join(self.tmpdir, 'target')
        link = join(self.tmpdir, 'link')
        open(target, 'w').close()
        symlink('/nonexistent/dead', link)

        assert prepare_symlink_target(target, link) == 'stale'
        assert not islink(link)
        assert not exists(link + '.bak')


class TestCreateSymlink(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_creates_symlink(self):
        target = join(self.tmpdir, 'target')
        link = join(self.tmpdir, 'link')
        open(target, 'w').close()
        create_symlink(target, link)
        assert islink(link)
        assert readlink(link) == target

    def test_creates_parent_dirs(self):
        target = join(self.tmpdir, 'target')
        link = join(self.tmpdir, 'deep', 'nested', 'link')
        open(target, 'w').close()
        create_symlink(target, link)
        assert islink(link)


# -- Table-driven: check_status --


class TestCheckStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = join(self.tmpdir, 'dotfiles')
        self.home = join(self.tmpdir, 'home')
        makedirs(self.repo)
        makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _entry(self, repo_path, source_path):
        return {'id': 'test', 'source_path': source_path, 'repo_path': repo_path}

    def test_status(self):
        cases = [
            ('healthy', '✓', True),
            ('missing', 'MISSING', False),
            ('not_symlink', 'NOT SYMLINK', False),
        ]
        for setup, expected_status, expected_ok in cases:
            with self.subTest(setup=setup):
                # Clean up from previous subtest
                repo_file = join(self.repo, '.bashrc')
                source_file = join(self.home, '.bashrc')
                for f in [repo_file, source_file]:
                    if islink(f):
                        unlink(f)
                    elif exists(f):
                        remove(f)

                if setup == 'healthy':
                    open(repo_file, 'w').close()
                    symlink(repo_file, source_file)
                elif setup == 'missing':
                    pass
                elif setup == 'not_symlink':
                    open(repo_file, 'w').close()
                    open(source_file, 'w').close()

                entry = self._entry('.bashrc', source_file)
                status, _, _, is_ok = check_status(entry, self.repo)
                assert is_ok == expected_ok
                assert expected_status in status


# -- Table-driven: bootstrap phases --


class BootstrapTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = join(self.tmpdir, 'dotfiles')
        self.home = join(self.tmpdir, 'home')
        makedirs(self.repo)
        makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)


BOOTSTRAP_CASES = [
    # (description,  dir_suffix,  filename,       os_type,  profile, should_link)
    ('common', None, '.bashrc', 'macos', None, True),
    ('os-specific', '__macos__', '.macos-thing', 'macos', None, True),
    ('profile', '__work__', '.work-config', 'macos', 'work', True),
]


class TestBootstrapPhases(BootstrapTestCase):
    def test_symlinks_phases(self):
        for desc, dir_suffix, filename, os_type, profile, should_link in BOOTSTRAP_CASES:
            with self.subTest(desc=desc):
                # Reset home dir between subtests
                shutil.rmtree(self.home)
                makedirs(self.home)

                target_dir = join(self.repo, dir_suffix) if dir_suffix else self.repo
                makedirs(target_dir, exist_ok=True)
                with open(join(target_dir, filename), 'w') as f:
                    f.write(desc)

                bootstrap(self.repo, self.home, os_type=os_type, profile=profile)

                link = join(self.home, filename)
                assert islink(link) == should_link


class TestBootstrapVariantFiltering(BootstrapTestCase):
    """Test that bootstrap filters OS/profile variant files correctly."""

    def test_skips_wrong_os_variants(self):
        # Create common + OS variant files
        for name in ['.zprofile', '.macos.zprofile', '.linux.zprofile']:
            with open(join(self.repo, name), 'w') as f:
                f.write(f'# {name}')

        bootstrap(self.repo, self.home, os_type='macos')

        assert islink(join(self.home, '.zprofile'))
        assert islink(join(self.home, '.macos.zprofile'))
        assert not exists(join(self.home, '.linux.zprofile'))

    def test_skips_wrong_profile_variants(self):
        for name in ['.gitconfig', '.work.gitconfig', '.home.gitconfig']:
            with open(join(self.repo, name), 'w') as f:
                f.write(f'# {name}')

        bootstrap(self.repo, self.home, os_type='macos', profile='work')

        assert islink(join(self.home, '.gitconfig'))
        assert islink(join(self.home, '.work.gitconfig'))
        assert not exists(join(self.home, '.home.gitconfig'))

    def test_generates_local_files(self):
        for name in ['.zprofile', '.macos.zprofile']:
            with open(join(self.repo, name), 'w') as f:
                f.write(f'# {name}')

        bootstrap(self.repo, self.home, os_type='macos')

        local_path = join(self.home, '.zprofile.local')
        assert exists(local_path)
        with open(local_path) as f:
            contents = f.read()
        assert '.macos.zprofile' in contents


class TestBootstrapBehavior(BootstrapTestCase):
    def test_raises_on_conflict(self):
        with open(join(self.repo, '.conflict'), 'w') as f:
            f.write('common')
        os_dir = join(self.repo, '__macos__')
        makedirs(os_dir)
        with open(join(os_dir, '.conflict'), 'w') as f:
            f.write('macos')

        with pytest.raises(ValueError):
            bootstrap(self.repo, self.home, os_type='macos')

    def test_idempotent(self):
        with open(join(self.repo, '.bashrc'), 'w') as f:
            f.write('# bash')

        bootstrap(self.repo, self.home, os_type='macos')
        bootstrap(self.repo, self.home, os_type='macos')  # should not fail

        assert islink(join(self.home, '.bashrc'))

    def test_creates_dotfiles_env(self):
        bootstrap(self.repo, self.home, os_type='linux', profile='home')

        env_path = join(self.home, '.dotfiles_env')
        content = open(env_path).read()
        assert 'DOTFILES_OS=linux' in content
        assert 'DOTFILES_PROFILE=home' in content

    def test_skip_registry(self):
        bootstrap(self.repo, self.home, os_type='macos', skip_registry=True)

    def test_dry_run_labels_would_update_for_existing_file(self):
        """A regular file sitting at the link path must be labeled would_update,
        not would_create — bootstrap will back it up and replace."""
        with open(join(self.repo, '.bashrc'), 'w') as f:
            f.write('# bash')
        with open(join(self.home, '.bashrc'), 'w') as f:
            f.write('# pre-existing')

        results = bootstrap(self.repo, self.home, os_type='macos', dry_run=True)

        actions = {link.rsplit('/', 1)[-1]: action for action, link, _, _ in results}
        assert actions['.bashrc'] == 'would_update', actions

    def test_dry_run_labels_would_update_for_existing_symlink(self):
        """A live symlink pointing somewhere else must be labeled would_update."""
        with open(join(self.repo, '.bashrc'), 'w') as f:
            f.write('# bash')
        other_target = join(self.tmpdir, 'other-file')
        with open(other_target, 'w') as f:
            f.write('# other')
        symlink(other_target, join(self.home, '.bashrc'))

        results = bootstrap(self.repo, self.home, os_type='macos', dry_run=True)

        actions = {link.rsplit('/', 1)[-1]: action for action, link, _, _ in results}
        assert actions['.bashrc'] == 'would_update', actions

    def test_dry_run_labels_would_create_for_absent(self):
        with open(join(self.repo, '.bashrc'), 'w') as f:
            f.write('# bash')

        results = bootstrap(self.repo, self.home, os_type='macos', dry_run=True)

        actions = {link.rsplit('/', 1)[-1]: action for action, link, _, _ in results}
        assert actions['.bashrc'] == 'would_create', actions


class TestDiscoverBootstrapManaged(BootstrapTestCase):
    def test_discovers_root_files(self):
        for name in ['.bashrc', '.zshrc']:
            open(join(self.repo, name), 'w').close()

        entries = discover_bootstrap_managed(
            self.repo, self.home, {'version': '1.0', 'registered_files': []}
        )
        ids = [e['id'] for e in entries]
        assert '(bootstrap) .bashrc' in ids
        assert '(bootstrap) .zshrc' in ids

    def test_excludes_registered_files(self):
        open(join(self.repo, '.bashrc'), 'w').close()

        entries = discover_bootstrap_managed(
            self.repo,
            self.home,
            {'version': '1.0', 'registered_files': [{'id': 'test', 'repo_path': '.bashrc'}]},
        )
        assert len(entries) == 0


class TestFindSymlinkDirs(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = join(self.tmpdir, 'home')
        makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_includes_home_dir(self):
        registry = {'registered_files': []}
        dirs = find_symlink_dirs(self.home, registry)
        assert self.home in dirs

    def test_includes_registry_source_parents(self):
        config_dir = join(self.home, '.config', 'zed')
        makedirs(config_dir)
        registry = {
            'registered_files': [
                {'source_path': join(config_dir, 'settings.json')},
            ]
        }
        dirs = find_symlink_dirs(self.home, registry)
        assert config_dir in dirs

    def test_skips_nonexistent_parents(self):
        registry = {
            'registered_files': [
                {'source_path': '/nonexistent/dir/file'},
            ]
        }
        dirs = find_symlink_dirs(self.home, registry)
        assert '/nonexistent/dir' not in dirs


class TestFindStaleSymlinks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_finds_broken_symlinks(self):
        dead_target = join(self.tmpdir, 'gone')
        link = join(self.tmpdir, '.old-config')
        symlink(dead_target, link)

        stale = find_stale_symlinks([self.tmpdir])
        assert len(stale) == 1
        assert stale[0][0] == link
        assert stale[0][1] == dead_target

    def test_ignores_healthy_symlinks(self):
        target = join(self.tmpdir, 'exists')
        open(target, 'w').close()
        symlink(target, join(self.tmpdir, 'link'))

        stale = find_stale_symlinks([self.tmpdir])
        assert len(stale) == 0

    def test_ignores_regular_files(self):
        open(join(self.tmpdir, 'regular'), 'w').close()

        stale = find_stale_symlinks([self.tmpdir])
        assert len(stale) == 0

    def test_skips_nonexistent_dirs(self):
        stale = find_stale_symlinks(['/nonexistent/dir'])
        assert len(stale) == 0

    def test_multiple_dirs(self):
        dir_a = join(self.tmpdir, 'a')
        dir_b = join(self.tmpdir, 'b')
        makedirs(dir_a)
        makedirs(dir_b)

        symlink('/gone1', join(dir_a, 'stale1'))
        symlink('/gone2', join(dir_b, 'stale2'))

        stale = find_stale_symlinks([dir_a, dir_b])
        assert len(stale) == 2


# -- .config/* convention auto-discovery (Unit 1) --


class TestListDotConfigChildren(unittest.TestCase):
    """Top-level children of <repo>/.config/ are scanned for the convention."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = join(self.tmpdir, 'dotfiles')
        makedirs(join(self.repo, '.config'))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _mkdir(self, *names):
        for name in names:
            makedirs(join(self.repo, '.config', name))

    def _touch(self, *names):
        for name in names:
            open(join(self.repo, '.config', name), 'w').close()

    def test_empty_when_no_config_dir(self):
        shutil.rmtree(join(self.repo, '.config'))
        assert list_dot_config_children(self.repo) == []

    def test_lists_directories_and_files(self):
        self._mkdir('fish', 'ghostty', 'zed')
        self._touch('standalone')
        assert list_dot_config_children(self.repo) == [
            'fish',
            'ghostty',
            'standalone',
            'zed',
        ]

    def test_respects_ignore_names(self):
        self._mkdir('fish', 'ghostty')
        assert list_dot_config_children(self.repo, ignore_names=['fish']) == ['ghostty']

    def test_skips_not_dotfiles_defaults(self):
        self._mkdir('fish', '.git')
        self._touch('.DS_Store')
        # .git always filtered (NOT_DOTFILES); .DS_Store not in defaults but
        # user should add it to ignore_dirs. For now, fish is only entry.
        # Actually .DS_Store is not in NOT_DOTFILES defaults — it's a file,
        # and would be listed. Users add it via registry ignore_files.
        children = list_dot_config_children(self.repo)
        assert 'fish' in children
        assert '.git' not in children

    def test_skips_md_extension(self):
        self._touch('README.md', 'notes.md')
        self._mkdir('tool')
        assert list_dot_config_children(self.repo) == ['tool']


class TestDiscoverBootstrapManagedDotConfig(unittest.TestCase):
    """discover_bootstrap_managed emits .config/* entries alongside root-level."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = join(self.tmpdir, 'dotfiles')
        self.home = join(self.tmpdir, 'home')
        makedirs(self.repo)
        makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _empty_registry(self):
        return {'version': '3.0', 'registered_files': []}

    def test_emits_dot_config_entries(self):
        makedirs(join(self.repo, '.config', 'fish'))
        makedirs(join(self.repo, '.config', 'ghostty'))
        entries = discover_bootstrap_managed(self.repo, self.home, self._empty_registry())
        sources = {e['source_path'] for e in entries}
        assert '~/.config/fish' in sources
        assert '~/.config/ghostty' in sources

    def test_dot_config_entry_shape(self):
        makedirs(join(self.repo, '.config', 'fish'))
        entries = discover_bootstrap_managed(self.repo, self.home, self._empty_registry())
        fish_entry = next(e for e in entries if e['source_path'] == '~/.config/fish')
        assert fish_entry['repo_path'] == '.config/fish'
        assert fish_entry['managed_by'] == 'bootstrap'
        assert fish_entry['category'] == '.config'
        assert fish_entry['os'] is None
        assert fish_entry['profile'] is None

    def test_registry_entry_takes_precedence(self):
        makedirs(join(self.repo, '.config', 'fish'))
        registry = {
            'version': '3.0',
            'registered_files': [
                {
                    'id': 'fish-explicit',
                    'source_path': '~/.config/fish',
                    'repo_path': '.config/fish',
                    'category': 'fish',
                    'os': None,
                    'profile': None,
                }
            ],
        }
        entries = discover_bootstrap_managed(self.repo, self.home, registry)
        # Registry entry dedups — bootstrap entry for same repo_path is skipped.
        sources = [e['source_path'] for e in entries if e['managed_by'] == 'bootstrap']
        assert '~/.config/fish' not in sources

    def test_respects_registry_ignore_dirs(self):
        makedirs(join(self.repo, '.config', 'fish'))
        makedirs(join(self.repo, '.config', 'private'))
        registry = {
            'version': '3.0',
            'registered_files': [],
            'ignore_dirs': ['private'],
        }
        entries = discover_bootstrap_managed(self.repo, self.home, registry)
        sources = {e['source_path'] for e in entries}
        assert '~/.config/fish' in sources
        assert '~/.config/private' not in sources


class TestBootstrapDotConfig(unittest.TestCase):
    """End-to-end bootstrap creates ~/.config/* symlinks from <repo>/.config/*."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = join(self.tmpdir, 'dotfiles')
        self.home = join(self.tmpdir, 'home')
        makedirs(join(self.repo, '.config', 'fish', 'conf.d'))
        makedirs(self.home)
        # A real file inside the fish dir so we can verify it's visible through the symlink.
        with open(join(self.repo, '.config', 'fish', 'config.fish'), 'w') as f:
            f.write('# fish config\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_directory_symlink_created(self):
        bootstrap(self.repo, self.home, 'macos')
        home_fish = join(self.home, '.config', 'fish')
        assert islink(home_fish)
        assert realpath(home_fish) == realpath(join(self.repo, '.config', 'fish'))

    def test_contents_visible_through_symlink(self):
        bootstrap(self.repo, self.home, 'macos')
        home_cfg = join(self.home, '.config', 'fish', 'config.fish')
        assert exists(home_cfg)
        with open(home_cfg) as f:
            assert 'fish config' in f.read()

    def test_pre_existing_home_dir_backed_up(self):
        # User already has ~/.config/fish/ as a real directory with content.
        home_fish = join(self.home, '.config', 'fish')
        makedirs(home_fish)
        with open(join(home_fish, 'pre-existing.fish'), 'w') as f:
            f.write('# pre-existing\n')

        bootstrap(self.repo, self.home, 'macos')

        # The directory is now a symlink to the repo.
        assert islink(home_fish)
        # Pre-existing content was backed up to a .bak neighbour.
        bak = home_fish + '.bak'
        assert isdir(bak)
        assert exists(join(bak, 'pre-existing.fish'))

    def test_idempotent_rerun(self):
        bootstrap(self.repo, self.home, 'macos')
        results = bootstrap(self.repo, self.home, 'macos')
        actions = [r[0] for r in results]
        # Second run should produce 'ok' for the already-linked entry, no 'created'.
        assert 'ok' in actions

    def test_dry_run_does_not_create(self):
        bootstrap(self.repo, self.home, 'macos', dry_run=True)
        home_fish = join(self.home, '.config', 'fish')
        assert not exists(home_fish)

    def test_no_config_dir_in_repo_skips_phase(self):
        shutil.rmtree(join(self.repo, '.config'))
        # Should not raise, and should not create anything under ~/.config.
        bootstrap(self.repo, self.home, 'macos')
        assert not exists(join(self.home, '.config'))


if __name__ == '__main__':
    unittest.main()
