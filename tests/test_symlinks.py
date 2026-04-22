"""Tests for lib.symlinks module."""

import os
import shutil
import tempfile
import unittest

import pytest

from dotgarden.symlinks import (
    bootstrap,
    check_status,
    create_symlink,
    discover_bootstrap_managed,
    find_stale_symlinks,
    find_symlink_dirs,
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
            open(os.path.join(self.tmpdir, name), 'w').close()

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
        os.makedirs(os.path.join(self.tmpdir, 'subdir'))
        assert list_dotfiles(self.tmpdir) == ['.bashrc']

    def test_returns_empty_for_nonexistent(self):
        assert list_dotfiles('/nonexistent/dir') == []


class TestPrepareSymlinkTarget(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_needed_when_link_missing(self):
        target = os.path.join(self.tmpdir, 'target')
        open(target, 'w').close()
        assert prepare_symlink_target(target, os.path.join(self.tmpdir, 'link')) == 'needed'

    def test_ok_when_already_correct(self):
        target = os.path.join(self.tmpdir, 'target')
        link = os.path.join(self.tmpdir, 'link')
        open(target, 'w').close()
        os.symlink(target, link)
        assert prepare_symlink_target(target, link) == 'ok'

    def test_replaced_backs_up_conflicting_file(self):
        target = os.path.join(self.tmpdir, 'target')
        link = os.path.join(self.tmpdir, 'link')
        open(target, 'w').close()
        with open(link, 'w') as f:
            f.write('old')

        assert prepare_symlink_target(target, link) == 'replaced'
        assert not os.path.exists(link)
        assert os.path.exists(link + '.bak')

    def test_stale_removes_dead_symlink(self):
        target = os.path.join(self.tmpdir, 'target')
        link = os.path.join(self.tmpdir, 'link')
        open(target, 'w').close()
        os.symlink('/nonexistent/dead', link)

        assert prepare_symlink_target(target, link) == 'stale'
        assert not os.path.islink(link)
        assert not os.path.exists(link + '.bak')


class TestCreateSymlink(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_creates_symlink(self):
        target = os.path.join(self.tmpdir, 'target')
        link = os.path.join(self.tmpdir, 'link')
        open(target, 'w').close()
        create_symlink(target, link)
        assert os.path.islink(link)
        assert os.readlink(link) == target

    def test_creates_parent_dirs(self):
        target = os.path.join(self.tmpdir, 'target')
        link = os.path.join(self.tmpdir, 'deep', 'nested', 'link')
        open(target, 'w').close()
        create_symlink(target, link)
        assert os.path.islink(link)


# -- Table-driven: check_status --


class TestCheckStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmpdir, 'dotfiles')
        self.home = os.path.join(self.tmpdir, 'home')
        os.makedirs(self.repo)
        os.makedirs(self.home)

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
                repo_file = os.path.join(self.repo, '.bashrc')
                source_file = os.path.join(self.home, '.bashrc')
                for f in [repo_file, source_file]:
                    if os.path.islink(f):
                        os.unlink(f)
                    elif os.path.exists(f):
                        os.remove(f)

                if setup == 'healthy':
                    open(repo_file, 'w').close()
                    os.symlink(repo_file, source_file)
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
        self.repo = os.path.join(self.tmpdir, 'dotfiles')
        self.home = os.path.join(self.tmpdir, 'home')
        os.makedirs(self.repo)
        os.makedirs(self.home)

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
                os.makedirs(self.home)

                target_dir = os.path.join(self.repo, dir_suffix) if dir_suffix else self.repo
                os.makedirs(target_dir, exist_ok=True)
                with open(os.path.join(target_dir, filename), 'w') as f:
                    f.write(desc)

                bootstrap(self.repo, self.home, os_type=os_type, profile=profile)

                link = os.path.join(self.home, filename)
                assert os.path.islink(link) == should_link


class TestBootstrapVariantFiltering(BootstrapTestCase):
    """Test that bootstrap filters OS/profile variant files correctly."""

    def test_skips_wrong_os_variants(self):
        # Create common + OS variant files
        for name in ['.zprofile', '.macos.zprofile', '.linux.zprofile']:
            with open(os.path.join(self.repo, name), 'w') as f:
                f.write(f'# {name}')

        bootstrap(self.repo, self.home, os_type='macos')

        assert os.path.islink(os.path.join(self.home, '.zprofile'))
        assert os.path.islink(os.path.join(self.home, '.macos.zprofile'))
        assert not os.path.exists(os.path.join(self.home, '.linux.zprofile'))

    def test_skips_wrong_profile_variants(self):
        for name in ['.gitconfig', '.work.gitconfig', '.home.gitconfig']:
            with open(os.path.join(self.repo, name), 'w') as f:
                f.write(f'# {name}')

        bootstrap(self.repo, self.home, os_type='macos', profile='work')

        assert os.path.islink(os.path.join(self.home, '.gitconfig'))
        assert os.path.islink(os.path.join(self.home, '.work.gitconfig'))
        assert not os.path.exists(os.path.join(self.home, '.home.gitconfig'))

    def test_generates_local_files(self):
        for name in ['.zprofile', '.macos.zprofile']:
            with open(os.path.join(self.repo, name), 'w') as f:
                f.write(f'# {name}')

        bootstrap(self.repo, self.home, os_type='macos')

        local_path = os.path.join(self.home, '.zprofile.local')
        assert os.path.exists(local_path)
        with open(local_path) as f:
            contents = f.read()
        assert '.macos.zprofile' in contents


class TestBootstrapBehavior(BootstrapTestCase):
    def test_raises_on_conflict(self):
        with open(os.path.join(self.repo, '.conflict'), 'w') as f:
            f.write('common')
        os_dir = os.path.join(self.repo, '__macos__')
        os.makedirs(os_dir)
        with open(os.path.join(os_dir, '.conflict'), 'w') as f:
            f.write('macos')

        with pytest.raises(ValueError):
            bootstrap(self.repo, self.home, os_type='macos')

    def test_idempotent(self):
        with open(os.path.join(self.repo, '.bashrc'), 'w') as f:
            f.write('# bash')

        bootstrap(self.repo, self.home, os_type='macos')
        bootstrap(self.repo, self.home, os_type='macos')  # should not fail

        assert os.path.islink(os.path.join(self.home, '.bashrc'))

    def test_creates_dotfiles_env(self):
        bootstrap(self.repo, self.home, os_type='linux', profile='home')

        env_path = os.path.join(self.home, '.dotfiles_env')
        content = open(env_path).read()
        assert 'DOTFILES_OS=linux' in content
        assert 'DOTFILES_PROFILE=home' in content

    def test_skip_registry(self):
        bootstrap(self.repo, self.home, os_type='macos', skip_registry=True)

    def test_dry_run_labels_would_update_for_existing_file(self):
        """A regular file sitting at the link path must be labeled would_update,
        not would_create — bootstrap will back it up and replace."""
        with open(os.path.join(self.repo, '.bashrc'), 'w') as f:
            f.write('# bash')
        with open(os.path.join(self.home, '.bashrc'), 'w') as f:
            f.write('# pre-existing')

        results = bootstrap(self.repo, self.home, os_type='macos', dry_run=True)

        actions = {link.rsplit('/', 1)[-1]: action for action, link, _, _ in results}
        assert actions['.bashrc'] == 'would_update', actions

    def test_dry_run_labels_would_update_for_existing_symlink(self):
        """A live symlink pointing somewhere else must be labeled would_update."""
        with open(os.path.join(self.repo, '.bashrc'), 'w') as f:
            f.write('# bash')
        other_target = os.path.join(self.tmpdir, 'other-file')
        with open(other_target, 'w') as f:
            f.write('# other')
        os.symlink(other_target, os.path.join(self.home, '.bashrc'))

        results = bootstrap(self.repo, self.home, os_type='macos', dry_run=True)

        actions = {link.rsplit('/', 1)[-1]: action for action, link, _, _ in results}
        assert actions['.bashrc'] == 'would_update', actions

    def test_dry_run_labels_would_create_for_absent(self):
        with open(os.path.join(self.repo, '.bashrc'), 'w') as f:
            f.write('# bash')

        results = bootstrap(self.repo, self.home, os_type='macos', dry_run=True)

        actions = {link.rsplit('/', 1)[-1]: action for action, link, _, _ in results}
        assert actions['.bashrc'] == 'would_create', actions


class TestDiscoverBootstrapManaged(BootstrapTestCase):
    def test_discovers_root_files(self):
        for name in ['.bashrc', '.zshrc']:
            open(os.path.join(self.repo, name), 'w').close()

        entries = discover_bootstrap_managed(
            self.repo, self.home, {'version': '1.0', 'registered_files': []}
        )
        ids = [e['id'] for e in entries]
        assert '(bootstrap) .bashrc' in ids
        assert '(bootstrap) .zshrc' in ids

    def test_excludes_registered_files(self):
        open(os.path.join(self.repo, '.bashrc'), 'w').close()

        entries = discover_bootstrap_managed(
            self.repo,
            self.home,
            {'version': '1.0', 'registered_files': [{'id': 'test', 'repo_path': '.bashrc'}]},
        )
        assert len(entries) == 0


class TestFindSymlinkDirs(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = os.path.join(self.tmpdir, 'home')
        os.makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_includes_home_dir(self):
        registry = {'registered_files': []}
        dirs = find_symlink_dirs(self.home, registry)
        assert self.home in dirs

    def test_includes_registry_source_parents(self):
        config_dir = os.path.join(self.home, '.config', 'zed')
        os.makedirs(config_dir)
        registry = {
            'registered_files': [
                {'source_path': os.path.join(config_dir, 'settings.json')},
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
        dead_target = os.path.join(self.tmpdir, 'gone')
        link = os.path.join(self.tmpdir, '.old-config')
        os.symlink(dead_target, link)

        stale = find_stale_symlinks([self.tmpdir])
        assert len(stale) == 1
        assert stale[0][0] == link
        assert stale[0][1] == dead_target

    def test_ignores_healthy_symlinks(self):
        target = os.path.join(self.tmpdir, 'exists')
        open(target, 'w').close()
        os.symlink(target, os.path.join(self.tmpdir, 'link'))

        stale = find_stale_symlinks([self.tmpdir])
        assert len(stale) == 0

    def test_ignores_regular_files(self):
        open(os.path.join(self.tmpdir, 'regular'), 'w').close()

        stale = find_stale_symlinks([self.tmpdir])
        assert len(stale) == 0

    def test_skips_nonexistent_dirs(self):
        stale = find_stale_symlinks(['/nonexistent/dir'])
        assert len(stale) == 0

    def test_multiple_dirs(self):
        dir_a = os.path.join(self.tmpdir, 'a')
        dir_b = os.path.join(self.tmpdir, 'b')
        os.makedirs(dir_a)
        os.makedirs(dir_b)

        os.symlink('/gone1', os.path.join(dir_a, 'stale1'))
        os.symlink('/gone2', os.path.join(dir_b, 'stale2'))

        stale = find_stale_symlinks([dir_a, dir_b])
        assert len(stale) == 2


if __name__ == '__main__':
    unittest.main()
