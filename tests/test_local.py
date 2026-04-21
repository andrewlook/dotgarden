"""Tests for .local file generation and health checking."""

import os
import shutil
import tempfile
import unittest

import pytest
from dotgarden.config import (
    format_local_include,
    is_os_specific,
    is_profile_specific,
)
from dotgarden.symlinks import (
    check_local_health,
    find_variant_files,
    generate_local_files,
)

# -- is_os_specific / is_profile_specific --


IS_OS_CASES = [
    ('.macos.zprofile', 'macos'),
    ('.linux.tmux.conf', 'linux'),
    ('.zprofile', None),
    ('.work.gitconfig', None),
    ('plain-file', None),
]


@pytest.mark.parametrize('filename,expected', IS_OS_CASES, ids=[c[0] for c in IS_OS_CASES])
def test_is_os_specific(filename, expected):
    assert is_os_specific(filename) == expected


IS_PROFILE_CASES = [
    ('.work.gitconfig', 'work'),
    ('.home.zprofile', 'home'),
    ('.gitconfig', None),
    ('.macos.zprofile', None),
    ('plain-file', None),
]


@pytest.mark.parametrize(
    'filename,expected', IS_PROFILE_CASES, ids=[c[0] for c in IS_PROFILE_CASES]
)
def test_is_profile_specific(filename, expected):
    assert is_profile_specific(filename) == expected


# -- format_local_include --


FORMAT_CASES = [
    ('shell', '.macos.zprofile', '[[ -f ~/.macos.zprofile ]] && . ~/.macos.zprofile'),
    ('git', '.work.gitconfig', '[include]\n    path = .work.gitconfig'),
    ('tmux', '.macos.tmux.conf', 'source-file -q ~/.macos.tmux.conf'),
]


@pytest.mark.parametrize(
    'tool_type,variant,expected', FORMAT_CASES, ids=[c[0] for c in FORMAT_CASES]
)
def test_format_local_include(tool_type, variant, expected):
    assert format_local_include(tool_type, variant) == expected


# -- find_variant_files --


class TestFindVariantFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _touch(self, *names):
        for name in names:
            open(os.path.join(self.tmpdir, name), 'w').close()

    def test_finds_os_variants(self):
        self._touch('.zprofile', '.macos.zprofile', '.linux.zprofile')
        result = find_variant_files(self.tmpdir, 'macos')
        assert '.zprofile' in result
        assert '.macos.zprofile' in result['.zprofile']
        assert '.linux.zprofile' not in result['.zprofile']

    def test_finds_profile_variants(self):
        self._touch('.gitconfig', '.work.gitconfig', '.home.gitconfig')
        result = find_variant_files(self.tmpdir, 'macos', profile='work')
        assert '.gitconfig' in result
        assert '.work.gitconfig' in result['.gitconfig']
        assert '.home.gitconfig' not in result['.gitconfig']

    def test_finds_both_os_and_profile(self):
        self._touch('.zprofile', '.macos.zprofile', '.work.zprofile')
        result = find_variant_files(self.tmpdir, 'macos', profile='work')
        assert '.zprofile' in result
        assert len(result['.zprofile']) == 2

    def test_empty_when_no_variants(self):
        self._touch('.zprofile', '.gitconfig')
        result = find_variant_files(self.tmpdir, 'macos')
        assert result == {}

    def test_ignores_directories(self):
        self._touch('.macos.zprofile')
        os.makedirs(os.path.join(self.tmpdir, '.macos.config'))
        result = find_variant_files(self.tmpdir, 'macos')
        assert '.zprofile' in result


# -- generate_local_files --


class TestGenerateLocalFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmpdir, 'dotfiles')
        self.home = os.path.join(self.tmpdir, 'home')
        os.makedirs(self.repo)
        os.makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _touch_repo(self, *names):
        for name in names:
            open(os.path.join(self.repo, name), 'w').close()

    def test_creates_shell_local(self):
        self._touch_repo('.zprofile', '.macos.zprofile', '.work.zprofile')
        results = generate_local_files(self.repo, self.home, 'macos', profile='work')

        assert len(results) == 1
        action, path, contents = results[0]
        assert action == 'created'
        assert path.endswith('.zprofile.local')
        assert '.macos.zprofile' in contents
        assert '.work.zprofile' in contents
        assert '[[ -f' in contents

        # File was actually written
        assert os.path.exists(path)

    def test_creates_git_local(self):
        self._touch_repo('.gitconfig', '.work.gitconfig')
        results = generate_local_files(self.repo, self.home, 'macos', profile='work')

        assert len(results) == 1
        _, _, contents = results[0]
        assert '[include]' in contents
        assert 'path = .work.gitconfig' in contents

    def test_creates_tmux_local(self):
        self._touch_repo('.tmux.conf', '.macos.tmux.conf')
        results = generate_local_files(self.repo, self.home, 'macos')

        assert len(results) == 1
        _, _, contents = results[0]
        assert 'source-file -q' in contents

    def test_idempotent(self):
        self._touch_repo('.zprofile', '.macos.zprofile')
        generate_local_files(self.repo, self.home, 'macos')
        results = generate_local_files(self.repo, self.home, 'macos')

        assert results[0][0] == 'ok'

    def test_updates_stale_local(self):
        self._touch_repo('.zprofile', '.macos.zprofile')
        generate_local_files(self.repo, self.home, 'macos')

        # Add a profile variant
        self._touch_repo('.work.zprofile')
        results = generate_local_files(self.repo, self.home, 'macos', profile='work')

        assert results[0][0] == 'updated'

    def test_dry_run(self):
        self._touch_repo('.zprofile', '.macos.zprofile')
        results = generate_local_files(self.repo, self.home, 'macos', dry_run=True)

        assert results[0][0] == 'would_create'
        assert not os.path.exists(os.path.join(self.home, '.zprofile.local'))

    def test_no_variants_no_local(self):
        self._touch_repo('.zprofile')
        results = generate_local_files(self.repo, self.home, 'macos')
        assert results == []


# -- check_local_health --


class TestCheckLocalHealth(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmpdir, 'dotfiles')
        self.home = os.path.join(self.tmpdir, 'home')
        os.makedirs(self.repo)
        os.makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _touch_repo(self, *names):
        for name in names:
            open(os.path.join(self.repo, name), 'w').close()

    def _write_home(self, name, content=''):
        path = os.path.join(self.home, name)
        with open(path, 'w') as f:
            f.write(content)

    def test_healthy_returns_no_issues(self):
        self._touch_repo('.zprofile', '.macos.zprofile')
        generate_local_files(self.repo, self.home, 'macos')
        # Simulate main dotfile including .local
        self._write_home('.zprofile', '[[ -f ~/.zprofile.local ]] && . ~/.zprofile.local')

        issues = check_local_health(self.repo, self.home, 'macos')
        assert issues == []

    def test_missing_local_file(self):
        self._touch_repo('.zprofile', '.macos.zprofile')
        # Don't generate .local file

        issues = check_local_health(self.repo, self.home, 'macos')
        assert len(issues) == 1
        assert 'missing' in issues[0][1]

    def test_stale_local_file(self):
        self._touch_repo('.zprofile', '.macos.zprofile')
        generate_local_files(self.repo, self.home, 'macos')
        # Simulate main dotfile
        self._write_home('.zprofile', '[[ -f ~/.zprofile.local ]] && . ~/.zprofile.local')

        # Now add a profile variant — .local is stale
        self._touch_repo('.work.zprofile')

        issues = check_local_health(self.repo, self.home, 'macos', profile='work')
        assert any('stale' in issue for _, issue in issues)

    def test_main_dotfile_missing_include(self):
        self._touch_repo('.zprofile', '.macos.zprofile')
        generate_local_files(self.repo, self.home, 'macos')
        # Main dotfile exists but doesn't include .local
        self._write_home('.zprofile', '# no local include here')

        issues = check_local_health(self.repo, self.home, 'macos')
        assert any('does not include' in issue for _, issue in issues)


if __name__ == '__main__':
    unittest.main()
