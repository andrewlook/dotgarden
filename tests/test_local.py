"""Tests for .local file generation and health checking."""

import os
import shutil
import tempfile
import unittest

import pytest
import yaml
from dotgarden.config import (
    format_local_include,
    is_os_specific,
    is_profile_specific,
)
from dotgarden.symlinks import (
    build_local_contents,
    check_local_health,
    discover_overlay_managed,
    find_variant_files,
    generate_local_files,
    get_local_status,
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


# -- get_local_status with overlay --


class TestGetLocalStatusWithOverlay(unittest.TestCase):
    """Overlay-contributed variants should not make a healthy .local look stale.

    When an overlay declares `profile: work` and contributes a bare `.gitconfig`,
    bootstrap links it as `.work.gitconfig` and rebuilds `.gitconfig.local` to
    include it. `get_local_status` needs to consider that overlay-rename the
    same way, or it thinks the `.local` is missing an entry and flags a false ⚠.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmpdir, 'dotfiles')
        self.home = os.path.join(self.tmpdir, 'home')
        self.overlay = os.path.join(self.tmpdir, 'overlay')
        os.makedirs(self.repo)
        os.makedirs(self.home)
        os.makedirs(self.overlay)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _touch(self, directory, *names):
        for name in names:
            with open(os.path.join(directory, name), 'w') as f:
                f.write(f'# {name}\n')

    def _overlay_registry(self, profile='work'):
        data = {'version': '3.0', 'profile': profile}
        with open(os.path.join(self.overlay, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump(data, f, sort_keys=False)

    def _write_local_for(self, base_dotfile, variants):
        """Write the home .local file matching the expected merged contents."""
        local_path = os.path.join(self.home, f'{base_dotfile}.local')
        with open(local_path, 'w') as f:
            f.write(build_local_contents(base_dotfile, variants))

    def _write_base_including_local(self, base_dotfile):
        """Write a home base file that includes its .local (so the chain is healthy)."""
        include = format_local_include('shell', f'{base_dotfile}.local')
        if base_dotfile == '.gitconfig':
            include = format_local_include('git', f'{base_dotfile}.local')
        elif base_dotfile == '.tmux.conf':
            include = format_local_include('tmux', f'{base_dotfile}.local')
        with open(os.path.join(self.home, base_dotfile), 'w') as f:
            f.write(include + '\n')

    def test_overlay_bare_file_treated_as_profile_variant(self):
        # Main repo has a base .gitconfig but no profile variants.
        self._touch(self.repo, '.gitconfig')
        # Overlay declares profile: work and contributes bare .gitconfig.
        self._overlay_registry(profile='work')
        self._touch(self.overlay, '.gitconfig')
        # Simulate bootstrap output: .local file including .work.gitconfig,
        # and a base .gitconfig that includes .gitconfig.local.
        self._write_local_for('.gitconfig', ['.work.gitconfig'])
        self._write_base_including_local('.gitconfig')

        results = get_local_status(
            self.repo, self.home, 'macos', profile='work', overlay_dir=self.overlay
        )

        assert len(results) == 1
        info = results[0]
        assert info['dotfile'] == '.gitconfig'
        assert info['local_exists']
        assert info['local_fresh']
        assert info['base_includes_local']
        assert info['issues'] == []

    def test_overlay_variant_merges_with_main_variants(self):
        # Main has a macos variant for .zprofile; overlay contributes its own.
        self._touch(self.repo, '.zprofile', '.macos.zprofile')
        self._overlay_registry(profile='work')
        self._touch(self.overlay, '.zprofile')
        # Local file must list BOTH variants for freshness to pass.
        self._write_local_for('.zprofile', ['.macos.zprofile', '.work.zprofile'])
        self._write_base_including_local('.zprofile')

        results = get_local_status(
            self.repo, self.home, 'macos', profile='work', overlay_dir=self.overlay
        )

        info = next(r for r in results if r['dotfile'] == '.zprofile')
        assert info['local_fresh']
        assert info['issues'] == []

    def test_without_overlay_arg_local_looks_stale(self):
        # Same setup as the first test, but caller forgot to pass overlay_dir.
        # The .local file references .work.gitconfig, which the function can't
        # explain without overlay context — so it flags stale. This is the
        # regression this fix prevents.
        self._touch(self.repo, '.gitconfig')
        self._overlay_registry(profile='work')
        self._touch(self.overlay, '.gitconfig')
        self._write_local_for('.gitconfig', ['.work.gitconfig'])
        self._write_base_including_local('.gitconfig')

        results = get_local_status(self.repo, self.home, 'macos', profile='work')

        # No variants known → .gitconfig isn't even in the results.
        assert not any(r['dotfile'] == '.gitconfig' for r in results)

    def test_malformed_overlay_does_not_crash(self):
        # Overlay is missing __registry__.yaml — we should fall through to
        # main-only variants rather than raising (bootstrap surfaces the error).
        self._touch(self.repo, '.zprofile', '.macos.zprofile')
        self._touch(self.overlay, '.gitconfig')  # no registry
        self._write_local_for('.zprofile', ['.macos.zprofile'])
        self._write_base_including_local('.zprofile')

        results = get_local_status(self.repo, self.home, 'macos', overlay_dir=self.overlay)

        info = next(r for r in results if r['dotfile'] == '.zprofile')
        assert info['local_fresh']
        assert info['issues'] == []

    def test_overlay_dir_missing_is_ignored(self):
        # overlay_dir points at a path that doesn't exist — treat as no overlay.
        self._touch(self.repo, '.zprofile', '.macos.zprofile')
        self._write_local_for('.zprofile', ['.macos.zprofile'])
        self._write_base_including_local('.zprofile')

        results = get_local_status(self.repo, self.home, 'macos', overlay_dir='/nonexistent/path')

        info = next(r for r in results if r['dotfile'] == '.zprofile')
        assert info['local_fresh']


# -- discover_overlay_managed --


class TestDiscoverOverlayManaged(unittest.TestCase):
    """Overlay entries should surface in `dotfile status` under the overlay's profile."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = os.path.join(self.tmpdir, 'home')
        self.overlay = os.path.join(self.tmpdir, 'overlay')
        os.makedirs(self.home)
        os.makedirs(self.overlay)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_overlay_registry(self, profile='work', extra=None):
        data = {'version': '3.0', 'profile': profile}
        if extra:
            data.update(extra)
        with open(os.path.join(self.overlay, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump(data, f, sort_keys=False)

    def _touch_overlay(self, *names):
        for name in names:
            path = os.path.join(self.overlay, name)
            os.makedirs(os.path.dirname(path) or self.overlay, exist_ok=True)
            with open(path, 'w') as f:
                f.write(f'# {name}\n')

    def test_bare_root_dotfile_surfaces_with_rename(self):
        self._write_overlay_registry(profile='work')
        self._touch_overlay('.gitconfig', '.zprofile')

        entries = discover_overlay_managed(self.overlay, self.home, 'macos')

        by_source = {e['source_path']: e for e in entries}
        assert '~/.work.gitconfig' in by_source
        assert '~/.work.zprofile' in by_source
        for entry in entries:
            assert entry['managed_by'] == 'bootstrap'
            assert entry['profile'] == 'work'
            assert os.path.isabs(entry['repo_path'])

    def test_overlay_registry_entries_included(self):
        self._write_overlay_registry(
            profile='work',
            extra={'boxy': [{'_boxy/init.sh': '~/.boxy/profile/init.sh'}]},
        )
        self._touch_overlay('_boxy/init.sh')

        entries = discover_overlay_managed(self.overlay, self.home, 'macos')

        boxy = [e for e in entries if e.get('category') == 'boxy']
        assert len(boxy) == 1
        assert boxy[0]['source_path'] == '~/.boxy/profile/init.sh'
        assert boxy[0]['repo_path'] == os.path.join(self.overlay, '_boxy/init.sh')
        assert boxy[0]['profile'] == 'work'

    def test_missing_overlay_returns_empty(self):
        assert discover_overlay_managed(None, self.home, 'macos') == []
        assert discover_overlay_managed('/nonexistent', self.home, 'macos') == []

    def test_malformed_overlay_registry_returns_empty(self):
        # No __registry__.yaml in the overlay → can't determine profile.
        self._touch_overlay('.gitconfig')
        assert discover_overlay_managed(self.overlay, self.home, 'macos') == []

    def test_prefixed_overlay_filenames_are_skipped(self):
        # Overlays must use bare filenames; bootstrap rejects prefixes.
        # discover skips them silently (bootstrap surfaces the error).
        self._write_overlay_registry(profile='work')
        self._touch_overlay('.gitconfig', '.macos.zprofile', '.work.zshrc')

        entries = discover_overlay_managed(self.overlay, self.home, 'macos')

        sources = {e['source_path'] for e in entries}
        assert '~/.work.gitconfig' in sources
        assert not any('macos.zprofile' in s for s in sources)
        assert not any('work.zshrc' in s and '.work.' not in s[3:] for s in sources)


if __name__ == '__main__':
    unittest.main()
