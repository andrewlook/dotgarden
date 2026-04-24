"""Tests for `dotfile specialize` — OS/profile variant scaffolding.

Covers root-level dotfiles (`.gitconfig` → `.macos.gitconfig`, etc.) and
nested `.config/<tool>/<base>` paths (`.config/fish/config.fish` →
`.config/fish/config.macos.fish`, etc.).
"""

import shutil
import tempfile
import unittest
from argparse import Namespace
from os import makedirs  # noqa: TID251
from os.path import dirname, exists, join  # noqa: TID251
from unittest.mock import patch

import pytest
import yaml

from dotgarden.cli.commands.specialize import cmd_specialize


class SpecializeTestCase(unittest.TestCase):
    """Shared setup: patch config.defaults to point at a tmp repo."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.fake_home = join(self.tmpdir, 'home')
        self.fake_repo = join(self.tmpdir, 'dotfiles')
        makedirs(self.fake_home)
        makedirs(self.fake_repo)
        self.cfg = {
            'dotfiles_dir': self.fake_repo,
            'home_dir': self.fake_home,
            'registry_path': join(self.fake_repo, '__registry__.yaml'),
        }
        self.defaults_patcher = patch('dotgarden.config.defaults', return_value=self.cfg)
        self.defaults_patcher.start()

    def tearDown(self):
        self.defaults_patcher.stop()
        shutil.rmtree(self.tmpdir)

    def _write_registry(self, **extras):
        data = {'version': '3.0', **extras}
        with open(self.cfg['registry_path'], 'w') as f:
            yaml.safe_dump(data, f, sort_keys=False)

    def _touch(self, rel, contents=''):
        path = join(self.fake_repo, rel)
        makedirs(dirname(path) or self.fake_repo, exist_ok=True)
        with open(path, 'w') as f:
            f.write(contents)
        return path

    def _args(self, kind, dotfile, dry_run=False):
        return Namespace(kind=kind, dotfile=dotfile, dry_run=dry_run)

    def _read(self, rel):
        with open(join(self.fake_repo, rel)) as f:
            return f.read()


# -- Root-level specialization --


class TestSpecializeRootOs(SpecializeTestCase):
    def test_creates_os_variants_from_registry(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.gitconfig', '[user]\n    name = Test\n')

        cmd_specialize(self._args('os', '.gitconfig'))

        assert exists(join(self.fake_repo, '.macos.gitconfig'))
        assert exists(join(self.fake_repo, '.linux.gitconfig'))

    def test_adds_git_include_to_base(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.gitconfig', '[user]\n    name = Test\n')

        cmd_specialize(self._args('os', '.gitconfig'))

        assert '[include]' in self._read('.gitconfig')
        assert '.gitconfig.local' in self._read('.gitconfig')

    def test_adds_shell_include_for_zprofile(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.zprofile', 'export PATH=$PATH\n')

        cmd_specialize(self._args('os', '.zprofile'))

        assert '[[ -f ~/.zprofile.local ]] && . ~/.zprofile.local' in self._read('.zprofile')

    def test_adds_tmux_include(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.tmux.conf', 'set -g mouse on\n')

        cmd_specialize(self._args('os', '.tmux.conf'))

        assert 'source-file -q ~/.tmux.conf.local' in self._read('.tmux.conf')

    def test_uses_default_os_when_registry_missing_key(self):
        self._write_registry()  # no 'os' key
        self._touch('.gitconfig', '')

        cmd_specialize(self._args('os', '.gitconfig'))

        # DEFAULT_OS_NAMES is ['macos', 'linux']
        assert exists(join(self.fake_repo, '.macos.gitconfig'))
        assert exists(join(self.fake_repo, '.linux.gitconfig'))

    def test_normalizes_missing_leading_dot(self):
        # Accept `gitconfig` as input; treat as `.gitconfig`.
        self._write_registry(os=['macos'])
        self._touch('.gitconfig', '')

        cmd_specialize(self._args('os', 'gitconfig'))

        assert exists(join(self.fake_repo, '.macos.gitconfig'))

    def test_idempotent_skip_existing(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.gitconfig', '')
        self._touch('.macos.gitconfig', '# pre-existing')

        cmd_specialize(self._args('os', '.gitconfig'))

        # Existing file is untouched; linux variant was created.
        assert self._read('.macos.gitconfig') == '# pre-existing'
        assert exists(join(self.fake_repo, '.linux.gitconfig'))

    def test_does_not_duplicate_include_line(self):
        self._write_registry(os=['macos'])
        self._touch('.gitconfig', '[include]\n    path = .gitconfig.local\n')

        cmd_specialize(self._args('os', '.gitconfig'))

        content = self._read('.gitconfig')
        assert content.count('[include]') == 1

    def test_dry_run_writes_nothing(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.gitconfig', '')

        cmd_specialize(self._args('os', '.gitconfig', dry_run=True))

        assert not exists(join(self.fake_repo, '.macos.gitconfig'))
        assert self._read('.gitconfig') == ''

    def test_missing_dotfile_errors(self):
        self._write_registry(os=['macos'])

        with pytest.raises(SystemExit):
            cmd_specialize(self._args('os', '.nonexistent'))


class TestSpecializeRootProfile(SpecializeTestCase):
    def test_creates_profile_variants(self):
        self._write_registry(profiles=['work', 'home'])
        self._touch('.zprofile', '')

        cmd_specialize(self._args('profile', '.zprofile'))

        assert exists(join(self.fake_repo, '.work.zprofile'))
        assert exists(join(self.fake_repo, '.home.zprofile'))


# -- Nested .config/<tool>/ specialization (new behavior) --


class TestSpecializeNested(SpecializeTestCase):
    def test_creates_nested_os_variants(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.config/fish/config.fish', 'set -gx EDITOR nvim\n')

        cmd_specialize(self._args('os', '.config/fish/config.fish'))

        assert exists(join(self.fake_repo, '.config/fish/config.macos.fish'))
        assert exists(join(self.fake_repo, '.config/fish/config.linux.fish'))

    def test_creates_nested_profile_variants(self):
        self._write_registry(profiles=['work', 'home'])
        self._touch('.config/fish/config.fish', '')

        cmd_specialize(self._args('profile', '.config/fish/config.fish'))

        assert exists(join(self.fake_repo, '.config/fish/config.work.fish'))
        assert exists(join(self.fake_repo, '.config/fish/config.home.fish'))

    def test_nested_include_uses_fish_syntax(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.config/fish/config.fish', '')

        cmd_specialize(self._args('os', '.config/fish/config.fish'))

        content = self._read('.config/fish/config.fish')
        assert 'test -e' in content
        assert 'and source' in content
        assert 'config.fish.local' in content

    def test_nested_dry_run(self):
        self._write_registry(os=['macos'])
        self._touch('.config/fish/config.fish', '')

        cmd_specialize(self._args('os', '.config/fish/config.fish', dry_run=True))

        assert not exists(join(self.fake_repo, '.config/fish/config.macos.fish'))

    def test_nested_extensionless_ghostty(self):
        self._write_registry(os=['macos'])
        # Ghostty's config file is extensionless — but ghostty isn't in
        # LOCAL_TOOL_TYPES / get_tool_type, so specialize errors out.
        self._touch('.config/ghostty/config', 'theme = catppuccin\n')

        with pytest.raises(SystemExit):
            cmd_specialize(self._args('os', '.config/ghostty/config'))

    def test_unknown_tool_type_errors(self):
        # zed .json has no include syntax.
        self._write_registry(os=['macos'])
        self._touch('.config/zed/settings.json', '{}')

        with pytest.raises(SystemExit):
            cmd_specialize(self._args('os', '.config/zed/settings.json'))

    def test_nested_idempotent(self):
        self._write_registry(os=['macos', 'linux'])
        self._touch('.config/fish/config.fish', '')
        cmd_specialize(self._args('os', '.config/fish/config.fish'))
        # Second run should not raise, not duplicate the include.
        cmd_specialize(self._args('os', '.config/fish/config.fish'))
        content = self._read('.config/fish/config.fish')
        assert content.count('source ~/.config/fish/config.fish.local') == 1


if __name__ == '__main__':
    unittest.main()
