"""Tests for overlay directory support in bootstrap.

Under the "overlay = one implicit profile" model (2026-04-20 strategy update,
decision 4), every overlay:

- Must contain `__registry__.yaml` with at least `version: '3.0'` and a
  `profile: <name>` top-level field. Bootstrap uses that field as the
  active profile for everything in the overlay.
- Uses BARE filenames for its dotfiles — `.gitconfig`, not `.work.gitconfig`.
  Bootstrap renames them to `.<profile>.<basename>` at link time so they
  flow through the existing `.local` hub.
- Does NOT nest `.<os>.<name>` or `.<profile>.<name>` variants — those are
  rejected. (OS variants inside an overlay are a v2 concern.)
"""

import os
import shutil
import tempfile
import unittest
from os import makedirs, readlink  # noqa: TID251
from os.path import basename, dirname, exists, islink, join  # noqa: TID251

import pytest
import yaml

from dotgarden.symlinks import bootstrap


class OverlayTestBase(unittest.TestCase):
    """Shared setUp/tearDown + helper for writing overlay registry with profile."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo = join(self.tmpdir, 'dotfiles')
        self.home = join(self.tmpdir, 'home')
        self.overlay = join(self.tmpdir, 'overlay')
        makedirs(self.repo)
        makedirs(self.home)
        makedirs(self.overlay)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _touch(self, directory, *names):
        for name in names:
            path = join(directory, name)
            makedirs(dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(f'# {name}')

    def _overlay_registry(self, profile='work', extra=None):
        """Write the overlay's required __registry__.yaml with profile declared."""
        data = {'version': '3.0', 'profile': profile}
        if extra:
            data.update(extra)
        with open(join(self.overlay, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump(data, f, sort_keys=False)


class TestOverlayBootstrapLinking(OverlayTestBase):
    """Overlay dotfiles get symlinked to HOME under the overlay's profile prefix."""

    def test_overlay_bare_file_renamed_on_link(self):
        """Overlay's `.gitconfig` (bare) links to `~/.work.gitconfig`."""
        self._overlay_registry(profile='work')
        self._touch(self.overlay, '.gitconfig')

        bootstrap(self.repo, self.home, os_type='macos', profile='work', overlay_dir=self.overlay)

        # NOT at ~/.gitconfig — that name is reserved for main-repo content.
        assert not exists(join(self.home, '.gitconfig'))
        # Linked at ~/.work.gitconfig — the profile-prefixed name.
        link = join(self.home, '.work.gitconfig')
        assert islink(link)
        target = readlink(link)
        # Target is the bare filename in the overlay.
        assert target.endswith('/.gitconfig'), target

    def test_overlay_and_main_coexist(self):
        """Main's `.bashrc` at `~/.bashrc`, overlay's `.bashrc` at `~/.work.bashrc`."""
        self._overlay_registry(profile='work')
        self._touch(self.repo, '.bashrc')
        self._touch(self.overlay, '.bashrc')

        bootstrap(self.repo, self.home, os_type='macos', profile='work', overlay_dir=self.overlay)

        main_link = join(self.home, '.bashrc')
        overlay_link = join(self.home, '.work.bashrc')
        assert islink(main_link)
        assert islink(overlay_link)
        assert self.repo in readlink(main_link)
        assert self.overlay in readlink(overlay_link)

    def test_overlay_os_prefixed_filename_rejected(self):
        """OS variants inside an overlay are not supported in v1."""
        self._overlay_registry(profile='work')
        self._touch(self.overlay, '.macos.zprofile')

        with pytest.raises(ValueError) as exc_info:
            bootstrap(
                self.repo, self.home, os_type='macos', profile='work', overlay_dir=self.overlay
            )
        assert '.macos.zprofile' in str(exc_info.value)
        assert 'OS' in str(exc_info.value)

    def test_overlay_profile_prefixed_filename_rejected(self):
        """Profile prefix inside overlay filename is redundant and rejected."""
        self._overlay_registry(profile='work')
        self._touch(self.overlay, '.work.gitconfig')

        with pytest.raises(ValueError) as exc_info:
            bootstrap(
                self.repo, self.home, os_type='macos', profile='work', overlay_dir=self.overlay
            )
        assert '.work.gitconfig' in str(exc_info.value)

    def test_overlay_missing_registry_raises(self):
        """Overlay without __registry__.yaml → clear error."""
        # Note: no _overlay_registry() call.
        self._touch(self.overlay, '.gitconfig')

        from dotgarden.registry import RegistryError

        with pytest.raises(RegistryError) as exc_info:
            bootstrap(self.repo, self.home, os_type='macos', overlay_dir=self.overlay)
        msg = str(exc_info.value)
        assert 'missing __registry__.yaml' in msg
        assert 'profile: <name>' in msg

    def test_overlay_missing_profile_field_raises(self):
        """Overlay registry without `profile:` → clear error."""
        from dotgarden.registry import RegistryError

        # Write a registry WITHOUT profile:
        with open(join(self.overlay, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump({'version': '3.0'}, f)
        self._touch(self.overlay, '.gitconfig')

        with pytest.raises(RegistryError) as exc_info:
            bootstrap(self.repo, self.home, os_type='macos', overlay_dir=self.overlay)
        assert 'missing' in str(exc_info.value).lower()
        assert 'profile' in str(exc_info.value)


class TestOverlayLocalFiles(OverlayTestBase):
    """The `.local` hub picks up overlay-renamed files automatically."""

    def test_overlay_content_in_local_hub(self):
        """Overlay's `.zprofile` (bare) → `~/.work.zprofile` + included in `.zprofile.local`."""
        self._overlay_registry(profile='work')
        self._touch(self.repo, '.zprofile', '.macos.zprofile')
        self._touch(self.overlay, '.zprofile')  # bare filename in overlay

        bootstrap(self.repo, self.home, os_type='macos', profile='work', overlay_dir=self.overlay)

        # Overlay file linked at the profile-prefixed name
        assert islink(join(self.home, '.work.zprofile'))

        # .local file includes BOTH the OS variant (from main) and the
        # profile variant (renamed from overlay)
        local_path = join(self.home, '.zprofile.local')
        assert exists(local_path)
        with open(local_path) as f:
            contents = f.read()
        assert '.macos.zprofile' in contents
        assert '.work.zprofile' in contents


class TestOverlayAbsence(OverlayTestBase):
    """Bootstrap without an overlay behaves exactly as pre-overlay."""

    def test_overlay_none_is_noop(self):
        self._touch(self.repo, '.gitconfig')

        results = bootstrap(self.repo, self.home, os_type='macos', overlay_dir=None)

        assert islink(join(self.home, '.gitconfig'))
        assert not any(phase == 'overlay' for _, _, _, phase in results)

    def test_overlay_nonexistent_dir_ignored(self):
        """Bootstrap is robust when the overlay path doesn't exist.

        (cli.py:cmd_bootstrap performs the user-facing existence check and
        errors out. The symlinks.bootstrap() layer is defensive — if called
        with a missing path, it silently skips the overlay phase.)
        """
        self._touch(self.repo, '.gitconfig')

        results = bootstrap(self.repo, self.home, os_type='macos', overlay_dir='/nonexistent/path')
        assert islink(join(self.home, '.gitconfig'))
        assert not any(phase == 'overlay' for _, _, _, phase in results)


class TestDotfilesEnv(OverlayTestBase):
    """`.dotfiles_env` round-tripping across bootstrap runs."""

    def test_dotfiles_env_includes_overlay(self):
        self._overlay_registry(profile='work')
        self._touch(self.repo, '.gitconfig')

        bootstrap(self.repo, self.home, os_type='linux', profile='work', overlay_dir=self.overlay)

        env_path = join(self.home, '.dotfiles_env')
        with open(env_path) as f:
            contents = f.read()
        assert 'DOTFILES_OVERLAY' in contents
        assert self.overlay in contents

    def test_dotfiles_env_no_overlay_when_none(self):
        self._touch(self.repo, '.gitconfig')

        bootstrap(self.repo, self.home, os_type='linux')

        env_path = join(self.home, '.dotfiles_env')
        with open(env_path) as f:
            contents = f.read()
        assert 'DOTFILES_OVERLAY' not in contents

    def test_dotfiles_env_no_profile_when_unset(self):
        """Regression: profile=None must not be written as the literal string 'None'."""
        self._touch(self.repo, '.gitconfig')

        bootstrap(self.repo, self.home, os_type='linux', profile=None)

        env_path = join(self.home, '.dotfiles_env')
        with open(env_path) as f:
            contents = f.read()
        assert 'DOTFILES_PROFILE' not in contents
        assert 'None' not in contents

    def test_dotfiles_env_shebang_has_no_leading_space(self):
        """The shebang must start at column 0 or shells won't honor it."""
        self._touch(self.repo, '.gitconfig')

        bootstrap(self.repo, self.home, os_type='linux')

        env_path = join(self.home, '.dotfiles_env')
        with open(env_path) as f:
            first_line = f.readline()
        assert first_line.startswith('#!/bin/bash')

    def test_dotfiles_env_preserves_user_lines(self):
        """Bootstrap must not drop user-added export lines from .dotfiles_env."""
        self._touch(self.repo, '.gitconfig')
        env_path = join(self.home, '.dotfiles_env')
        with open(env_path, 'w') as f:
            f.write('#!/bin/bash\n')
            f.write('export DOTFILES_OS=linux\n')
            f.write('export MY_WORK_TOKEN=abc123\n')
            f.write('export CUSTOM_VAR="hello world"\n')

        bootstrap(self.repo, self.home, os_type='linux')

        with open(env_path) as f:
            contents = f.read()
        assert 'MY_WORK_TOKEN=abc123' in contents
        assert 'CUSTOM_VAR="hello world"' in contents
        # Exactly one managed DOTFILES_OS line.
        assert contents.count('export DOTFILES_OS=') == 1


class TestRegistryInteraction(OverlayTestBase):
    def test_overlay_registry_duplicate_source_path_skipped(self):
        """Overlay registry entry with same source_path as main registry is skipped."""
        target = join(self.home, '.config', 'foo', 'bar')
        makedirs(dirname(target), exist_ok=True)

        main_body = join(self.repo, '_foo', 'bar')
        overlay_body = join(self.overlay, '_foo', 'bar')
        makedirs(dirname(main_body), exist_ok=True)
        makedirs(dirname(overlay_body), exist_ok=True)
        with open(main_body, 'w') as f:
            f.write('main')
        with open(overlay_body, 'w') as f:
            f.write('overlay')

        # Main registry — no profile
        with open(join(self.repo, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump({'version': '3.0', 'foo': [{'_foo/bar': '~/.config/foo/bar'}]}, f)
        # Overlay registry — declares profile + has same entry
        self._overlay_registry(profile='work', extra={'foo': [{'_foo/bar': '~/.config/foo/bar'}]})

        bootstrap(self.repo, self.home, os_type='macos', overlay_dir=self.overlay)

        bak = os.path.expanduser('~/.config/foo/bar.bak')  # noqa: TID251  (CLITestCase monkey-patches os.path.expanduser)
        assert not exists(bak), 'overlay should not have backed up the main symlink'

    def test_registry_ignore_files_excludes_from_bootstrap(self):
        """Registry-level ignore_files entry must exclude a file from bootstrap."""
        self._touch(self.repo, '.zshrc', 'custom-script.py')
        with open(join(self.repo, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump({'version': '3.0', 'ignore_files': ['custom-script.py']}, f)

        bootstrap(self.repo, self.home, os_type='macos')

        assert islink(join(self.home, '.zshrc'))
        assert not exists(join(self.home, 'custom-script.py'))


# -- Overlay .config/<tool>/ nested pre-naming (Unit 4) --


class TestOverlayDotConfigPreNaming(OverlayTestBase):
    """Overlay files under .config/<tool>/ must pre-name the modifier.

    No auto-renaming happens for nested paths — users must commit files
    like `config.work.fish` (not bare `config.fish`) in the overlay.
    """

    def _write_main_base(self, *paths):
        """Place base files in the main repo's .config/<tool>/ structure."""
        for p in paths:
            full = join(self.repo, p)
            makedirs(dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(f'# {basename(p)}\n')

    def _write_overlay_nested(self, *paths):
        for p in paths:
            full = join(self.overlay, p)
            makedirs(dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(f'# overlay {basename(p)}\n')

    def test_properly_named_overlay_file_accepted(self):
        self._overlay_registry(profile='work')
        self._write_main_base('.config/fish/config.fish')
        self._write_overlay_nested('.config/fish/config.work.fish')

        bootstrap(self.repo, self.home, 'linux', profile='work', overlay_dir=self.overlay)

        # .local was generated and references the overlay's absolute path.
        local_path = join(self.home, '.config', 'fish', 'config.fish.local')
        assert exists(local_path)
        with open(local_path) as f:
            content = f.read()
        overlay_abs = join(self.overlay, '.config', 'fish', 'config.work.fish')
        assert overlay_abs in content

    def test_bare_overlay_file_rejected(self):
        # Overlay has .config/fish/config.fish (no modifier) — must error.
        self._overlay_registry(profile='work')
        self._write_main_base('.config/fish/config.fish')
        self._write_overlay_nested('.config/fish/config.fish')

        with pytest.raises(Exception) as exc_info:
            bootstrap(self.repo, self.home, 'linux', profile='work', overlay_dir=self.overlay)
        assert 'no modifier' in str(exc_info.value)
        assert 'config.fish' in str(exc_info.value)

    def test_wrong_profile_overlay_file_rejected(self):
        # Overlay is profile=work but file is config.home.fish.
        self._overlay_registry(profile='work')
        self._write_main_base('.config/fish/config.fish')
        self._write_overlay_nested('.config/fish/config.home.fish')

        with pytest.raises(Exception) as exc_info:
            bootstrap(self.repo, self.home, 'linux', profile='work', overlay_dir=self.overlay)
        assert "'home'" in str(exc_info.value) and "'work'" in str(exc_info.value)

    def test_os_tagged_overlay_file_accepted(self):
        # Overlay has .config/fish/config.linux.fish — OS-tagged, any profile.
        self._overlay_registry(profile='work')
        self._write_main_base('.config/fish/config.fish')
        self._write_overlay_nested('.config/fish/config.linux.fish')

        bootstrap(self.repo, self.home, 'linux', profile='work', overlay_dir=self.overlay)

        local_path = join(self.home, '.config', 'fish', 'config.fish.local')
        assert exists(local_path)
        with open(local_path) as f:
            content = f.read()
        overlay_abs = join(self.overlay, '.config', 'fish', 'config.linux.fish')
        assert overlay_abs in content

    def test_os_tagged_overlay_file_filtered_by_current_os(self):
        # Overlay's config.macos.fish should NOT be included on linux bootstrap.
        self._overlay_registry(profile='work')
        self._write_main_base('.config/fish/config.fish')
        self._write_overlay_nested('.config/fish/config.macos.fish')

        bootstrap(self.repo, self.home, 'linux', profile='work', overlay_dir=self.overlay)

        local_path = join(self.home, '.config', 'fish', 'config.fish.local')
        # .local might not even exist if no variants matched.
        if exists(local_path):
            with open(local_path) as f:
                content = f.read()
            assert 'config.macos.fish' not in content

    def test_overlay_without_config_dir_does_not_crash(self):
        # Overlay with just root-level bare files and no .config/ dir.
        self._overlay_registry(profile='work')
        self._touch(self.overlay, '.gitconfig')
        self._write_main_base('.config/fish/config.fish')

        # Should not crash in _validate_overlay_dot_config.
        bootstrap(self.repo, self.home, 'linux', profile='work', overlay_dir=self.overlay)


if __name__ == '__main__':
    unittest.main()
