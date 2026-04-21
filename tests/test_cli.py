"""Integration tests for lib.cli subcommands."""

import os
import shutil
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch

import pytest
from dotgarden import registry as reg
from dotgarden.cli import (
    _apply_dotfile_home_override,
    cmd_bootstrap,
    cmd_ids,
    cmd_register,
    cmd_unregister,
)


class CLITestCase(unittest.TestCase):
    """Base class that patches config.defaults() to use a temp directory."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.fake_home = os.path.join(self.tmpdir, 'home')
        self.fake_repo = os.path.join(self.tmpdir, 'dotfiles')
        os.makedirs(self.fake_home)
        os.makedirs(self.fake_repo)

        self.cfg = {
            'dotfiles_dir': self.fake_repo,
            'home_dir': self.fake_home,
            'registry_path': os.path.join(self.fake_repo, 'registry.yaml'),
        }
        # Patch config.defaults at its source module. Pre-refactor this was
        # `dotgarden.cli.config.defaults` because cli was a single file that
        # imported config. Under the cli/commands/ subpackage, each command
        # imports `from dotgarden import config` independently; patching the
        # source covers every importer without drifting per-command.
        self.defaults_patcher = patch('dotgarden.config.defaults', return_value=self.cfg)
        self.defaults_patcher.start()

        self.orig_expanduser = os.path.expanduser
        os.path.expanduser = lambda p: p.replace('~', self.fake_home) if p.startswith('~') else p

    def tearDown(self):
        self.defaults_patcher.stop()
        os.path.expanduser = self.orig_expanduser
        shutil.rmtree(self.tmpdir)

    def create_source_file(self, rel_path, content='test'):
        abs_path = os.path.join(self.fake_home, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w') as f:
            f.write(content)
        return abs_path

    def register(
        self, path, category=None, os_flag=None, profile=None, name=None, dry_run=False, force=False
    ):
        args = Namespace(
            path=path,
            category=category,
            os=os_flag,
            profile=profile,
            name=name,
            dry_run=dry_run,
            force=force,
        )
        with patch('builtins.input', return_value='y'):
            cmd_register(args)

    def load_registry(self):
        return reg.load(self.cfg['registry_path'])


# -- Table-driven: register placement --

REGISTER_PLACEMENT_CASES = [
    # (rel_path,                                                  kwargs,                                      expected_repo_path,        expected_category)
    ('.bashrc', {}, '.bashrc', 'uncategorized'),
    (
        'Library/Application Support/Cursor/User/keybindings.json',
        {'category': 'cursor'},
        '_cursor/keybindings.json',
        'cursor',
    ),
    (
        'Library/Application Support/Cursor/User/settings.json',
        {'category': 'cursor', 'os_flag': 'macos'},
        '_cursor/settings.json',
        'cursor',
    ),
    ('.macos-thing', {'os_flag': 'macos'}, '__macos__/.macos-thing', 'uncategorized'),
]


class TestRegisterPlacement(CLITestCase):
    def test_placement(self):
        for rel_path, kwargs, expected_repo_path, expected_category in REGISTER_PLACEMENT_CASES:
            with self.subTest(expected_repo_path=expected_repo_path):
                # Reset registry between subtests
                if os.path.exists(self.cfg['registry_path']):
                    os.remove(self.cfg['registry_path'])

                src = self.create_source_file(rel_path)
                self.register(src, **kwargs)

                entry = self.load_registry()['registered_files'][0]
                self.assertEqual(entry['repo_path'], expected_repo_path)
                self.assertEqual(entry['category'], expected_category)

                # Clean up symlink for next subtest
                if os.path.islink(src):
                    os.unlink(src)


# -- Table-driven: auto-detect category --

AUTO_DETECT_REGISTER_CASES = [
    # (rel_path,                                                  expected_category)
    ('Library/Application Support/Code/User/settings.json', 'vscode'),
    ('Library/Application Support/Cursor/User/keybindings.json', 'cursor'),
    ('.config/nvim/init.lua', 'nvim'),
]


class TestRegisterAutoDetect(CLITestCase):
    def test_auto_detect(self):
        for rel_path, expected_category in AUTO_DETECT_REGISTER_CASES:
            with self.subTest(expected_category=expected_category):
                if os.path.exists(self.cfg['registry_path']):
                    os.remove(self.cfg['registry_path'])

                src = self.create_source_file(rel_path)
                self.register(src)

                entry = self.load_registry()['registered_files'][0]
                self.assertEqual(entry['category'], expected_category)

                if os.path.islink(src):
                    os.unlink(src)


# -- Non-table tests for behavior that needs unique setup --


class TestRegisterEdgeCases(CLITestCase):
    def test_dry_run(self):
        src = self.create_source_file('.testrc')
        args = Namespace(
            path=src,
            category=None,
            os=None,
            profile=None,
            name=None,
            dry_run=True,
            force=False,
        )
        cmd_register(args)

        assert len(self.load_registry()['registered_files']) == 0
        assert not os.path.islink(src)

    def test_duplicate_fails(self):
        src = self.create_source_file('.duprc')
        self.register(src)

        os.unlink(src)
        with open(src, 'w') as f:
            f.write('dup')

        with pytest.raises(SystemExit):
            self.register(src)

    def test_custom_name(self):
        src = self.create_source_file('.bashrc')
        self.register(src, name='bash-config')

        entry = self.load_registry()['registered_files'][0]
        assert entry['repo_path'] == 'bash-config'

    def test_symlink_points_to_repo(self):
        src = self.create_source_file('.zshrc', content='# zsh')
        self.register(src)

        target = os.readlink(src)
        assert target == os.path.join(self.fake_repo, '.zshrc')
        with open(src) as f:
            assert f.read() == '# zsh'


class TestRegisterOverlayRouting(CLITestCase):
    """`dotfile register --overlay <dir>` writes to the overlay instead of main."""

    def setUp(self):
        super().setUp()
        self.overlay_dir = os.path.join(self.tmpdir, 'overlay')
        os.makedirs(self.overlay_dir)
        # Minimum overlay: __registry__.yaml with profile declared.
        import yaml

        with open(os.path.join(self.overlay_dir, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump({'version': '3.0', 'profile': 'work'}, f)

    def _overlay_registry(self):
        return reg.load(os.path.join(self.overlay_dir, '__registry__.yaml'))

    def _register_with_overlay(self, path, profile=None):
        args = Namespace(
            path=path,
            category=None,
            os=None,
            profile=profile,
            name=None,
            dry_run=False,
            force=False,
            overlay=self.overlay_dir,
            yes=True,  # skip the confirmation prompt
        )
        cmd_register(args)

    def test_register_routes_file_to_overlay(self):
        """File moves into overlay_dir, not main repo; overlay registry updated."""
        src = self.create_source_file('.config/myapp/settings.json')

        self._register_with_overlay(src)

        # Symlink at the source still points somewhere; target lives in overlay
        assert os.path.islink(src)
        target = os.readlink(src)
        assert target.startswith(self.overlay_dir), f'expected target in overlay, got {target}'

        # Main registry is untouched
        main_reg = self.load_registry()
        assert len(main_reg['registered_files']) == 0

        # Overlay registry has the new entry
        overlay_reg = self._overlay_registry()
        assert len(overlay_reg['registered_files']) == 1
        entry = overlay_reg['registered_files'][0]
        # Overlay preserves its profile declaration across writes
        assert overlay_reg['profile'] == 'work'
        # Entry is implicitly profile=work (inferred from overlay metadata)
        assert entry['profile'] == 'work'

    def test_register_infers_profile_from_overlay(self):
        """--profile omitted → inferred from overlay's declared profile."""
        src = self.create_source_file('.config/inferme/cfg')

        self._register_with_overlay(src, profile=None)

        overlay_reg = self._overlay_registry()
        entry = overlay_reg['registered_files'][0]
        assert entry['profile'] == 'work'

    def test_register_rejects_profile_mismatch(self):
        """--profile home with overlay profile:work → SystemExit."""
        src = self.create_source_file('.config/myapp/cfg')

        with pytest.raises(SystemExit):
            self._register_with_overlay(src, profile='home')

        # Nothing was moved: source is still a regular file
        assert os.path.isfile(src) and not os.path.islink(src)
        # Overlay registry still has no entries
        overlay_reg = self._overlay_registry()
        assert len(overlay_reg['registered_files']) == 0

    def test_register_errors_on_nonexistent_overlay(self):
        """--overlay pointing at a missing path → SystemExit, no side effects."""
        src = self.create_source_file('.config/myapp/cfg')
        args = Namespace(
            path=src,
            category=None,
            os=None,
            profile=None,
            name=None,
            dry_run=False,
            force=False,
            overlay=os.path.join(self.tmpdir, 'does-not-exist'),
            yes=True,
        )
        with pytest.raises(SystemExit):
            cmd_register(args)
        assert os.path.isfile(src) and not os.path.islink(src)

    def test_yes_flag_skips_prompt(self):
        """--yes means cmd_register doesn't call input()."""
        from unittest.mock import patch as mock_patch

        src = self.create_source_file('.config/consent/cfg')
        args = Namespace(
            path=src,
            category=None,
            os=None,
            profile=None,
            name=None,
            dry_run=False,
            force=False,
            overlay=self.overlay_dir,
            yes=True,
        )
        # Patch builtins.input so the test fails loudly if register tries to prompt
        with mock_patch(
            'builtins.input',
            side_effect=AssertionError('--yes should have short-circuited the confirmation prompt'),
        ):
            cmd_register(args)


class TestWizardColor(unittest.TestCase):
    """Named color helpers emit ANSI only when the environment allows.

    Tests exercise `color_label`, `color_hint`, `color_header` — the public
    API. The underlying `_use_color` gating is shared, so one helper is a
    stand-in for the behavior; the sibling test confirms the other two
    actually produce distinguishable output.
    """

    def test_color_applied_on_tty_without_no_color(self):
        """tty attached, NO_COLOR unset → escape codes emitted, reset appended."""
        from unittest.mock import patch as mock_patch

        from dotgarden.cli.utils.logging import color_label

        with (
            mock_patch('sys.stdout.isatty', return_value=True),
            mock_patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop('NO_COLOR', None)
            out = color_label('hi')
        assert out.startswith('\033[')
        assert out.endswith('\033[0m')
        assert 'hi' in out

    def test_color_stripped_when_no_color_env(self):
        """NO_COLOR=1 → plain text, no escapes, even on a tty."""
        from unittest.mock import patch as mock_patch

        from dotgarden.cli.utils.logging import color_label

        with (
            mock_patch('sys.stdout.isatty', return_value=True),
            mock_patch.dict(os.environ, {'NO_COLOR': '1'}),
        ):
            out = color_label('hi')
        assert out == 'hi'

    def test_color_stripped_when_non_tty(self):
        """stdout not a tty → plain text, even without NO_COLOR."""
        from unittest.mock import patch as mock_patch

        from dotgarden.cli.utils.logging import color_label

        with mock_patch('sys.stdout.isatty', return_value=False):
            os.environ.pop('NO_COLOR', None)
            out = color_label('hi')
        assert out == 'hi'

    def test_three_helpers_emit_distinguishable_codes(self):
        """color_label / color_hint / color_header each use a different ANSI code.

        Regression guard: if someone accidentally collapses them all into
        one wrapper they'd fail silently — the tests above only check that
        ONE escape code is emitted, not that each helper uses its own.
        """
        from unittest.mock import patch as mock_patch

        from dotgarden.cli.utils.logging import color_header, color_hint, color_label

        with mock_patch('sys.stdout.isatty', return_value=True):
            os.environ.pop('NO_COLOR', None)
            label = color_label('x')
            hint = color_hint('x')
            header = color_header('x')

        # Each wraps the same text differently — the leading code before
        # the literal 'x' must be unique per helper.
        codes = {s[: s.index('x')] for s in (label, hint, header)}
        assert len(codes) == 3, f'expected 3 distinct codes, got {codes}'


class TestRegisterWizard(CLITestCase):
    """Interactive wizard prompts for missing fields on a tty.

    Flag-provided and `--yes` paths skip the wizard. Non-tty invocations
    (tests, CI, piped invocations) also skip it, which is how the rest of
    the test suite doesn't need to mock anything.
    """

    def _args(self, path, **overrides):
        defaults = dict(
            path=path,
            category=None,
            os=None,
            profile=None,
            name=None,
            dry_run=False,
            force=False,
            overlay=None,
            yes=False,  # wizard is ENABLED
        )
        defaults.update(overrides)
        return Namespace(**defaults)

    def test_wizard_skipped_when_non_tty(self):
        """No prompts fire when stdin is not a tty (default pytest state).

        No patches: the harness's stdin is already not a tty, and --yes is
        False. The wizard short-circuits; cmd_register falls through to the
        existing y/N confirmation prompt which the test patches separately.
        """
        from unittest.mock import patch as mock_patch

        src = self.create_source_file('.config/app/x')
        # Only the final "Proceed?" prompt should fire — that's already gated
        # behind the tty check at the preview step, so patching input to
        # return 'y' is enough.
        with mock_patch('builtins.input', return_value='y'):
            cmd_register(self._args(src))

        entry = self.load_registry()['registered_files'][0]
        # No wizard = no prompts = defaults in place
        assert entry['os'] is None
        assert entry['profile'] is None

    def test_wizard_prompts_for_os_when_missing(self):
        """Simulate tty: wizard prompts for category, os, profile.

        Note: the v3 registry save/load only preserves a single condition
        per entry (os OR profile, never both — it's a known schema limit
        of the compact format). So this test verifies the wizard captures
        OS; a sibling test verifies it captures profile.
        """
        from unittest.mock import patch as mock_patch

        src = self.create_source_file('.config/widget/x')
        # Responses: accept auto-detected category, pick macos, leave
        # profile empty (default none), then 'y' to confirm.
        responses = iter(['', 'macos', '', 'y'])
        with (
            mock_patch('sys.stdin.isatty', return_value=True),
            mock_patch('builtins.input', side_effect=lambda prompt='': next(responses)),
        ):
            cmd_register(self._args(src))

        entry = self.load_registry()['registered_files'][0]
        assert entry['category'] == 'widget'  # auto-detected
        assert entry['os'] == 'macos'

    def test_wizard_prompts_for_profile_when_missing(self):
        """Wizard captures profile when os is left blank.

        Sibling to test_wizard_prompts_for_os_when_missing — exercises the
        other leg of the os-or-profile exclusivity in the save/load
        roundtrip.
        """
        from unittest.mock import patch as mock_patch

        src = self.create_source_file('.config/widget/x')
        # category default, os empty, profile=work, confirm
        responses = iter(['', '', 'work', 'y'])
        with (
            mock_patch('sys.stdin.isatty', return_value=True),
            mock_patch('builtins.input', side_effect=lambda prompt='': next(responses)),
        ):
            cmd_register(self._args(src))

        entry = self.load_registry()['registered_files'][0]
        assert entry['profile'] == 'work'
        assert entry['os'] is None

    def test_wizard_skips_prompt_for_field_provided_via_flag(self):
        """When a flag is provided, the wizard does NOT prompt for it.

        Pass `category='custom-cat'` explicitly: wizard skips the category
        prompt. It still prompts for os + profile (neither passed, no
        overlay) and the final Proceed?. If the wizard spuriously asked
        about category, StopIteration would fire from the response iterator.
        """
        from unittest.mock import patch as mock_patch

        src = self.create_source_file('.config/thing/x')
        # Expected prompts: os, profile, then Proceed?.
        responses = iter(['', 'work', 'y'])
        with (
            mock_patch('sys.stdin.isatty', return_value=True),
            mock_patch('builtins.input', side_effect=lambda prompt='': next(responses)),
        ):
            cmd_register(self._args(src, category='custom-cat'))

        entry = self.load_registry()['registered_files'][0]
        assert entry['category'] == 'custom-cat'  # flag respected
        assert entry['profile'] == 'work'  # from wizard prompt

    def test_wizard_skips_profile_prompt_when_overlay_active(self):
        """With overlay, profile is inferred from overlay metadata — no prompt."""
        from unittest.mock import patch as mock_patch

        import yaml

        overlay_dir = os.path.join(self.tmpdir, 'overlay-work')
        os.makedirs(overlay_dir)
        with open(os.path.join(overlay_dir, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump({'version': '3.0', 'profile': 'work'}, f)

        src = self.create_source_file('.config/thing/x')
        # Wizard prompts: category (accept default), os (accept none), then
        # final Proceed?. No profile prompt because overlay already set it.
        responses = iter(['', '', 'y'])
        with (
            mock_patch('sys.stdin.isatty', return_value=True),
            mock_patch('builtins.input', side_effect=lambda prompt='': next(responses)),
        ):
            cmd_register(self._args(src, overlay=overlay_dir))

        # Profile was inferred from overlay, not prompted
        overlay_reg = reg.load(os.path.join(overlay_dir, '__registry__.yaml'))
        entry = overlay_reg['registered_files'][0]
        assert entry['profile'] == 'work'


class TestCmdBootstrap(CLITestCase):
    def test_bootstrap_creates_symlinks(self):
        for name in ['.bashrc', '.zshrc']:
            with open(os.path.join(self.fake_repo, name), 'w') as f:
                f.write(f'# {name}')

        cmd_bootstrap(
            Namespace(os='macos', profile=None, skip_registry=False, dry_run=False, overlay=None)
        )

        for name in ['.bashrc', '.zshrc']:
            assert os.path.islink(os.path.join(self.fake_home, name))

    def test_bootstrap_requires_os(self):
        with pytest.raises(SystemExit):
            cmd_bootstrap(
                Namespace(os=None, profile=None, skip_registry=False, dry_run=False, overlay=None)
            )


class TestOverlayResolutionPrecedence(CLITestCase):
    """cmd_bootstrap resolves overlay in order: flag > env var > .dotfiles_env."""

    def setUp(self):
        super().setUp()
        self.overlay_flag = os.path.join(self.tmpdir, 'overlay-flag')
        self.overlay_env = os.path.join(self.tmpdir, 'overlay-env')
        self.overlay_saved = os.path.join(self.tmpdir, 'overlay-saved')
        # Each overlay needs a valid __registry__.yaml with profile declared
        # so cmd_bootstrap's overlay-profile validation doesn't error out.
        # All three declare the same profile so --profile=None cleanly
        # resolves to "work" whichever overlay wins the precedence fight.
        import yaml

        for d in (self.overlay_flag, self.overlay_env, self.overlay_saved):
            os.makedirs(d)
            with open(os.path.join(d, '__registry__.yaml'), 'w') as f:
                yaml.safe_dump({'version': '3.0', 'profile': 'work'}, f)

        # Patch symlinks.bootstrap where cmd_bootstrap imports it from.
        # Pre-refactor the target was `dotgarden.cli.symlinks.bootstrap`
        # (cli was a single file with `from dotgarden import symlinks`).
        # Under the subpackage layout, cmd_bootstrap lives in
        # `dotgarden.cli.commands.bootstrap` and imports `symlinks` as a
        # top-level module — so we patch there.
        self.bootstrap_patcher = patch(
            'dotgarden.cli.commands.bootstrap.symlinks.bootstrap', return_value=[]
        )
        self.bootstrap_mock = self.bootstrap_patcher.start()

    def tearDown(self):
        self.bootstrap_patcher.stop()
        super().tearDown()

    def _write_saved_overlay(self, path):
        env_path = os.path.join(self.fake_home, '.dotfiles_env')
        with open(env_path, 'w') as f:
            f.write(f'#!/bin/bash\nexport DOTFILES_OS=macos\nexport DOTFILES_OVERLAY={path}\n')

    def _call(self, overlay=None):
        cmd_bootstrap(
            Namespace(
                os='macos',
                profile=None,
                skip_registry=False,
                dry_run=False,
                overlay=overlay,
            )
        )
        return self.bootstrap_mock.call_args.kwargs['overlay_dir']

    def test_flag_wins_over_env_and_saved(self):
        with patch.dict(os.environ, {'DOTFILES_OVERLAY': self.overlay_env}):
            self._write_saved_overlay(self.overlay_saved)
            chosen = self._call(overlay=self.overlay_flag)
        assert chosen == self.overlay_flag

    def test_env_wins_over_saved_when_no_flag(self):
        with patch.dict(os.environ, {'DOTFILES_OVERLAY': self.overlay_env}):
            self._write_saved_overlay(self.overlay_saved)
            chosen = self._call(overlay=None)
        assert chosen == self.overlay_env

    def test_saved_used_when_flag_and_env_absent(self):
        env = {k: v for k, v in os.environ.items() if k != 'DOTFILES_OVERLAY'}
        with patch.dict(os.environ, env, clear=True):
            self._write_saved_overlay(self.overlay_saved)
            chosen = self._call(overlay=None)
        assert chosen == self.overlay_saved

    def test_none_when_no_source_set(self):
        env = {k: v for k, v in os.environ.items() if k != 'DOTFILES_OVERLAY'}
        with patch.dict(os.environ, env, clear=True):
            chosen = self._call(overlay=None)
        assert chosen is None

    def test_missing_overlay_path_exits(self):
        """Explicit flag pointing at a nonexistent dir → SystemExit."""
        bad = os.path.join(self.tmpdir, 'does-not-exist')
        with pytest.raises(SystemExit):
            self._call(overlay=bad)


class TestCmdUnregister(CLITestCase):
    def test_unregister_restores_by_default(self):
        src = self.create_source_file('.bashrc', content='# my config')
        self.register(src)

        # Source is now a symlink, file is in repo
        assert os.path.islink(src)
        assert os.path.isfile(os.path.join(self.fake_repo, '.bashrc'))

        cmd_unregister(
            Namespace(
                id_or_path='bashrc',
                restore=True,
                keep_symlink=False,
                keep_file=False,
                dry_run=False,
            )
        )

        # Registry is empty
        assert len(self.load_registry()['registered_files']) == 0
        # File is restored (not a symlink)
        assert not os.path.islink(src)
        assert os.path.isfile(src)
        with open(src) as f:
            assert f.read() == '# my config'
        # Repo copy is removed
        assert not os.path.exists(os.path.join(self.fake_repo, '.bashrc'))

    def test_unregister_no_restore(self):
        src = self.create_source_file('.zshrc')
        self.register(src)

        cmd_unregister(
            Namespace(
                id_or_path='zshrc',
                restore=False,
                keep_symlink=False,
                keep_file=False,
                dry_run=False,
            )
        )

        assert len(self.load_registry()['registered_files']) == 0
        assert not os.path.islink(src)
        assert not os.path.exists(os.path.join(self.fake_repo, '.zshrc'))

    def test_unregister_dry_run(self):
        src = self.create_source_file('.vimrc')
        self.register(src)

        cmd_unregister(
            Namespace(
                id_or_path='vimrc', restore=True, keep_symlink=False, keep_file=False, dry_run=True
            )
        )

        # Nothing changed
        assert len(self.load_registry()['registered_files']) == 1
        assert os.path.islink(src)

    def test_unregister_by_repo_path(self):
        """Unregister using the repo path (e.g. _fish/config.fish)."""
        src = self.create_source_file('.config/nvim/init.lua', content='-- nvim')
        self.register(src)

        entry = self.load_registry()['registered_files'][0]
        repo_path = entry['repo_path']  # e.g. _nvim/init.lua

        cmd_unregister(
            Namespace(
                id_or_path=repo_path,
                restore=True,
                keep_symlink=False,
                keep_file=False,
                dry_run=False,
            )
        )

        assert len(self.load_registry()['registered_files']) == 0
        assert not os.path.islink(src)
        assert os.path.isfile(src)

    def test_unregister_by_source_path(self):
        """Unregister using the full source path."""
        src = self.create_source_file('.config/ghostty/config', content='font-size = 14')
        self.register(src)

        cmd_unregister(
            Namespace(
                id_or_path=src,
                restore=True,
                keep_symlink=False,
                keep_file=False,
                dry_run=False,
            )
        )

        assert len(self.load_registry()['registered_files']) == 0
        assert os.path.isfile(src)


class TestUnregisterSharedRepoPath(CLITestCase):
    """When multiple entries share the same repo_path (e.g. a skill symlinked
    to both ~/.claude/skills/ and ~/.codex/skills/), unregistering one must
    NOT delete the repo copy — the other entry still needs it."""

    def test_unregister_shared_keeps_repo_file(self):
        # Register first source
        src1 = self.create_source_file('.claude/skills/qa', content='# skill')
        self.register(src1, category='skills')

        # Manually add a second entry pointing to the same repo file
        registry = self.load_registry()
        first_entry = registry['registered_files'][0]
        second_entry = {
            'id': 'codex-skills-qa',
            'source_path': '~/.codex/skills/qa',
            'repo_path': first_entry['repo_path'],
            'category': 'skills',
            'os': None,
            'profile': None,
            'registered_at': '2026-01-01T00:00:00Z',
        }
        reg.add(registry, second_entry)
        reg.save(registry, self.cfg['registry_path'], self.fake_repo)

        # Create symlink for second entry
        second_source = os.path.join(self.fake_home, '.codex', 'skills', 'qa')
        os.makedirs(os.path.dirname(second_source), exist_ok=True)
        repo_abs = os.path.join(self.fake_repo, first_entry['repo_path'])
        os.symlink(repo_abs, second_source)

        # Unregister first entry (with restore)
        cmd_unregister(
            Namespace(
                id_or_path=first_entry['id'],
                restore=True,
                keep_symlink=False,
                keep_file=False,
                dry_run=False,
            )
        )

        # First source was restored (no longer a symlink)
        assert os.path.isfile(src1)
        assert not os.path.islink(src1)

        # Repo copy is still there (needed by second entry)
        assert os.path.exists(repo_abs)

        # Second symlink still works
        assert os.path.islink(second_source)
        assert os.path.exists(second_source)

        # Registry has one entry left (the codex symlink)
        remaining = self.load_registry()['registered_files']
        assert len(remaining) == 1
        assert remaining[0]['source_path'] == '~/.codex/skills/qa'


class TestCmdIds(CLITestCase):
    def test_ids_prints_registered_ids(self):
        src1 = self.create_source_file('.bashrc')
        src2 = self.create_source_file('.zshrc')
        self.register(src1)
        self.register(src2)

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_ids(Namespace())

        ids = buf.getvalue().strip().split('\n')
        assert 'bashrc' in ids
        assert 'zshrc' in ids
        assert len(ids) == 2

    def test_ids_empty_registry(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_ids(Namespace())

        assert buf.getvalue() == ''


class TestDotfileHomeOverride(unittest.TestCase):
    """DOTFILE_HOME env var redirects HOME for the entire CLI invocation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_home = os.environ.get('HOME')
        self.orig_dotfile_home = os.environ.pop('DOTFILE_HOME', None)

    def tearDown(self):
        if self.orig_home is not None:
            os.environ['HOME'] = self.orig_home
        if self.orig_dotfile_home is not None:
            os.environ['DOTFILE_HOME'] = self.orig_dotfile_home
        else:
            os.environ.pop('DOTFILE_HOME', None)
        shutil.rmtree(self.tmpdir)

    def test_unset_leaves_home_alone(self):
        pre = os.environ.get('HOME')
        _apply_dotfile_home_override()
        assert os.environ.get('HOME') == pre

    def test_set_to_existing_dir_replaces_home(self):
        fake_home = os.path.join(self.tmpdir, 'fake-home')
        os.makedirs(fake_home)
        os.environ['DOTFILE_HOME'] = fake_home
        _apply_dotfile_home_override()
        assert os.environ['HOME'] == fake_home
        # Subsequent os.path.expanduser uses the overridden HOME.
        assert os.path.expanduser('~') == fake_home

    def test_set_to_missing_dir_exits_nonzero(self):
        os.environ['DOTFILE_HOME'] = os.path.join(self.tmpdir, 'does-not-exist')
        with pytest.raises(SystemExit):
            _apply_dotfile_home_override()

    def test_relative_path_is_resolved_to_absolute(self):
        rel = 'fake-rel-home'
        abs_path = os.path.join(self.tmpdir, rel)
        os.makedirs(abs_path)
        cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            os.environ['DOTFILE_HOME'] = rel
            _apply_dotfile_home_override()
            assert os.path.isabs(os.environ['HOME'])
            # realpath to handle /var vs /private/var on macOS
            assert os.path.realpath(os.environ['HOME']) == os.path.realpath(abs_path)
        finally:
            os.chdir(cwd)

    def test_tilde_expansion(self):
        # Point DOTFILE_HOME at ~/<something> where HOME is temporarily our tmpdir
        nested = os.path.join(self.tmpdir, 'nested')
        os.makedirs(nested)
        os.environ['HOME'] = self.tmpdir
        os.environ['DOTFILE_HOME'] = '~/nested'
        _apply_dotfile_home_override()
        assert os.path.realpath(os.environ['HOME']) == os.path.realpath(nested)


if __name__ == '__main__':
    unittest.main()
