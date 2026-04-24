"""Integration tests for lib.cli subcommands."""

import os
import shutil
import tempfile
import unittest
from argparse import Namespace
from os import makedirs, readlink, remove, symlink, unlink  # noqa: TID251
from os.path import dirname, exists, isdir, isfile, islink, join, realpath  # noqa: TID251
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
        self.fake_home = join(self.tmpdir, 'home')
        self.fake_repo = join(self.tmpdir, 'dotfiles')
        makedirs(self.fake_home)
        makedirs(self.fake_repo)

        self.cfg = {
            'dotfiles_dir': self.fake_repo,
            'home_dir': self.fake_home,
            'registry_path': join(self.fake_repo, 'registry.yaml'),
        }
        # Patch config.defaults at its source module. Pre-refactor this was
        # `dotgarden.cli.config.defaults` because cli was a single file that
        # imported config. Under the cli/commands/ subpackage, each command
        # imports `from dotgarden import config` independently; patching the
        # source covers every importer without drifting per-command.
        self.defaults_patcher = patch('dotgarden.config.defaults', return_value=self.cfg)
        self.defaults_patcher.start()

        # Monkey-patch os.path.expanduser so CLI code (which uses
        # `os.path.expanduser` via `import os`) sees fake_home as `~`.
        # Must stay fully-qualified — the short `expanduser` import would
        # shadow the real module attribute and break the patch.
        self.orig_expanduser = os.path.expanduser  # noqa: TID251
        os.path.expanduser = (  # noqa: TID251
            lambda p: p.replace('~', self.fake_home) if p.startswith('~') else p
        )

    def tearDown(self):
        self.defaults_patcher.stop()
        os.path.expanduser = self.orig_expanduser  # noqa: TID251
        shutil.rmtree(self.tmpdir)

    def create_source_file(self, rel_path, content='test'):
        abs_path = join(self.fake_home, rel_path)
        makedirs(dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w') as f:
            f.write(content)
        return abs_path

    def register(
        self, path, category=None, os_flag=None, profile=None, name=None, dry_run=False, force=False
    ):
        # Since the convention-skip change, `register` with no --category/
        # --os/--profile/--name on a convention path skips the registry
        # entirely. Tests written before that feature expect every register
        # call through this helper to produce a registry entry. Preserve
        # that expectation by defaulting `category` to the auto-detected
        # value or 'uncategorized' — BUT only when all the other registry
        # triggers are absent. If the caller sets os_flag/profile/name, they
        # already opted into registry mode via those signals and we don't
        # want to override the repo_dir choice (os_flag routes into __os__/,
        # not _<category>/).
        if category is None and name is None and os_flag is None and profile is None:
            from dotgarden import paths as _paths

            auto = _paths.auto_detect_category(path, self.fake_home)
            category = auto or 'uncategorized'
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
    # (rel_path, kwargs, expected_repo_path, expected_category)
    #
    # `.bashrc` with no kwargs goes through the test helper which forces
    # category='uncategorized' (see CLITestCase.register docstring) — so
    # the resulting repo path is under _uncategorized/.
    ('.bashrc', {}, '_uncategorized/.bashrc', 'uncategorized'),
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
    # Registry save roundtrips entries with no explicit category under
    # the 'uncategorized' key, so that's what comes back on load.
    ('.macos-thing', {'os_flag': 'macos'}, '__macos__/.macos-thing', 'uncategorized'),
]


class TestRegisterPlacement(CLITestCase):
    def test_placement(self):
        for rel_path, kwargs, expected_repo_path, expected_category in REGISTER_PLACEMENT_CASES:
            with self.subTest(expected_repo_path=expected_repo_path):
                # Reset registry between subtests
                if exists(self.cfg['registry_path']):
                    remove(self.cfg['registry_path'])

                src = self.create_source_file(rel_path)
                self.register(src, **kwargs)

                entry = self.load_registry()['registered_files'][0]
                self.assertEqual(entry['repo_path'], expected_repo_path)
                self.assertEqual(entry['category'], expected_category)

                # Clean up symlink for next subtest
                if islink(src):
                    unlink(src)


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
                if exists(self.cfg['registry_path']):
                    remove(self.cfg['registry_path'])

                src = self.create_source_file(rel_path)
                self.register(src)

                entry = self.load_registry()['registered_files'][0]
                self.assertEqual(entry['category'], expected_category)

                if islink(src):
                    unlink(src)


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
        assert not islink(src)

    def test_duplicate_fails(self):
        src = self.create_source_file('.duprc')
        self.register(src)

        unlink(src)
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
        # Helper routes .zshrc through registry mode with the
        # 'uncategorized' category (see CLITestCase.register), so the repo
        # path is _uncategorized/.zshrc. The link content round-trips the
        # user's original bytes regardless of where they land in the repo.
        src = self.create_source_file('.zshrc', content='# zsh')
        self.register(src)

        target = readlink(src)
        assert target == join(self.fake_repo, '_uncategorized', '.zshrc')
        with open(src) as f:
            assert f.read() == '# zsh'


class TestRegisterOverlayRouting(CLITestCase):
    """`dotfile register --overlay <dir>` writes to the overlay instead of main."""

    def setUp(self):
        super().setUp()
        self.overlay_dir = join(self.tmpdir, 'overlay')
        makedirs(self.overlay_dir)
        # Minimum overlay: __registry__.yaml with profile declared.
        import yaml

        with open(join(self.overlay_dir, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump({'version': '3.0', 'profile': 'work'}, f)

    def _overlay_registry(self):
        return reg.load(join(self.overlay_dir, '__registry__.yaml'))

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
        assert islink(src)
        target = readlink(src)
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
        assert isfile(src) and not islink(src)
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
            overlay=join(self.tmpdir, 'does-not-exist'),
            yes=True,
        )
        with pytest.raises(SystemExit):
            cmd_register(args)
        assert isfile(src) and not islink(src)

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

        Uses a `Library/…`-style path so register lands in registry mode
        (non-convention target) and we can read the resulting entry to
        confirm no wizard-populated fields leaked in.
        """
        from unittest.mock import patch as mock_patch

        src = self.create_source_file('Library/app/x')
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

        overlay_dir = join(self.tmpdir, 'overlay-work')
        makedirs(overlay_dir)
        with open(join(overlay_dir, '__registry__.yaml'), 'w') as f:
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
        overlay_reg = reg.load(join(overlay_dir, '__registry__.yaml'))
        entry = overlay_reg['registered_files'][0]
        assert entry['profile'] == 'work'


class TestCmdBootstrap(CLITestCase):
    def test_bootstrap_creates_symlinks(self):
        for name in ['.bashrc', '.zshrc']:
            with open(join(self.fake_repo, name), 'w') as f:
                f.write(f'# {name}')

        cmd_bootstrap(
            Namespace(os='macos', profile=None, skip_registry=False, dry_run=False, overlay=None)
        )

        for name in ['.bashrc', '.zshrc']:
            assert islink(join(self.fake_home, name))

    def test_bootstrap_requires_os(self):
        with pytest.raises(SystemExit):
            cmd_bootstrap(
                Namespace(os=None, profile=None, skip_registry=False, dry_run=False, overlay=None)
            )


class TestOverlayResolutionPrecedence(CLITestCase):
    """cmd_bootstrap resolves overlay in order: flag > env var > .dotfiles_env."""

    def setUp(self):
        super().setUp()
        self.overlay_flag = join(self.tmpdir, 'overlay-flag')
        self.overlay_env = join(self.tmpdir, 'overlay-env')
        self.overlay_saved = join(self.tmpdir, 'overlay-saved')
        # Each overlay needs a valid __registry__.yaml with profile declared
        # so cmd_bootstrap's overlay-profile validation doesn't error out.
        # All three declare the same profile so --profile=None cleanly
        # resolves to "work" whichever overlay wins the precedence fight.
        import yaml

        for d in (self.overlay_flag, self.overlay_env, self.overlay_saved):
            makedirs(d)
            with open(join(d, '__registry__.yaml'), 'w') as f:
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
        env_path = join(self.fake_home, '.dotfiles_env')
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
        bad = join(self.tmpdir, 'does-not-exist')
        with pytest.raises(SystemExit):
            self._call(overlay=bad)


class TestCmdUnregister(CLITestCase):
    # Since convention-eligible paths now skip the registry, the tests here
    # use the CLITestCase.register helper which forces category to auto-detect
    # or 'uncategorized'. Files land under _<category>/, and unregister is
    # invoked with the matching ID (e.g. `uncategorized-bashrc`).
    def test_unregister_restores_by_default(self):
        src = self.create_source_file('.bashrc', content='# my config')
        self.register(src)

        repo_path = join(self.fake_repo, '_uncategorized', '.bashrc')
        assert islink(src)
        assert isfile(repo_path)

        cmd_unregister(
            Namespace(
                id_or_path='uncategorized-bashrc',
                restore=True,
                keep_symlink=False,
                keep_file=False,
                dry_run=False,
            )
        )

        assert len(self.load_registry()['registered_files']) == 0
        assert not islink(src)
        assert isfile(src)
        with open(src) as f:
            assert f.read() == '# my config'
        assert not exists(repo_path)

    def test_unregister_no_restore(self):
        src = self.create_source_file('.zshrc')
        self.register(src)

        cmd_unregister(
            Namespace(
                id_or_path='uncategorized-zshrc',
                restore=False,
                keep_symlink=False,
                keep_file=False,
                dry_run=False,
            )
        )

        assert len(self.load_registry()['registered_files']) == 0
        assert not islink(src)
        assert not exists(join(self.fake_repo, '_uncategorized', '.zshrc'))

    def test_unregister_dry_run(self):
        src = self.create_source_file('.vimrc')
        self.register(src)

        cmd_unregister(
            Namespace(
                id_or_path='uncategorized-vimrc',
                restore=True,
                keep_symlink=False,
                keep_file=False,
                dry_run=True,
            )
        )

        # Nothing changed
        assert len(self.load_registry()['registered_files']) == 1
        assert islink(src)

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
        assert not islink(src)
        assert isfile(src)

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
        assert isfile(src)


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
        second_source = join(self.fake_home, '.codex', 'skills', 'qa')
        makedirs(dirname(second_source), exist_ok=True)
        repo_abs = join(self.fake_repo, first_entry['repo_path'])
        symlink(repo_abs, second_source)

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
        assert isfile(src1)
        assert not islink(src1)

        # Repo copy is still there (needed by second entry)
        assert exists(repo_abs)

        # Second symlink still works
        assert islink(second_source)
        assert exists(second_source)

        # Registry has one entry left (the codex symlink)
        remaining = self.load_registry()['registered_files']
        assert len(remaining) == 1
        assert remaining[0]['source_path'] == '~/.codex/skills/qa'


class TestCmdIds(CLITestCase):
    def test_ids_prints_registered_ids(self):
        # Helper forces 'uncategorized' category for these root-dotfile paths,
        # so the derived IDs look like 'uncategorized-bashrc'.
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
        assert 'uncategorized-bashrc' in ids
        assert 'uncategorized-zshrc' in ids
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
        fake_home = join(self.tmpdir, 'fake-home')
        makedirs(fake_home)
        os.environ['DOTFILE_HOME'] = fake_home
        _apply_dotfile_home_override()
        assert os.environ['HOME'] == fake_home
        # Subsequent os.path.expanduser uses the overridden HOME.
        assert os.path.expanduser('~') == fake_home  # noqa: TID251

    def test_set_to_missing_dir_exits_nonzero(self):
        os.environ['DOTFILE_HOME'] = join(self.tmpdir, 'does-not-exist')
        with pytest.raises(SystemExit):
            _apply_dotfile_home_override()

    def test_relative_path_is_resolved_to_absolute(self):
        rel = 'fake-rel-home'
        abs_path = join(self.tmpdir, rel)
        makedirs(abs_path)
        cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            os.environ['DOTFILE_HOME'] = rel
            _apply_dotfile_home_override()
            assert os.path.isabs(os.environ['HOME'])
            # realpath to handle /var vs /private/var on macOS
            assert realpath(os.environ['HOME']) == realpath(abs_path)
        finally:
            os.chdir(cwd)

    def test_tilde_expansion(self):
        # Point DOTFILE_HOME at ~/<something> where HOME is temporarily our tmpdir
        nested = join(self.tmpdir, 'nested')
        makedirs(nested)
        os.environ['HOME'] = self.tmpdir
        os.environ['DOTFILE_HOME'] = '~/nested'
        _apply_dotfile_home_override()
        assert realpath(os.environ['HOME']) == realpath(nested)


class TestColorizeTarget(unittest.TestCase):
    """Status command target-path colorizer routes by which base dir owns the path."""

    def setUp(self):
        from dotgarden.cli.commands.status import _REPO_COLOR, _RESET, _colorize_target

        self.colorize = _colorize_target
        self.repo_color = _REPO_COLOR
        self.reset = _RESET
        self.overlay_color = '\033[38;5;215m'

    def test_main_repo_prefix_colored_suffix_plain(self):
        result = self.colorize('~/dotfiles/.aliases', '~/dotfiles', None, None)
        assert result == f'{self.repo_color}~/dotfiles{self.reset}/.aliases'

    def test_exact_main_repo_path_fully_colored(self):
        result = self.colorize('~/dotfiles', '~/dotfiles', None, None)
        assert result == f'{self.repo_color}~/dotfiles{self.reset}'

    def test_overlay_prefix_colored_suffix_plain(self):
        result = self.colorize(
            '~/tools/dotfiles-work/.gitconfig',
            '~/dotfiles',
            '~/tools/dotfiles-work',
            self.overlay_color,
        )
        assert result == (f'{self.overlay_color}~/tools/dotfiles-work{self.reset}/.gitconfig')

    def test_path_under_neither_stays_uncolored(self):
        result = self.colorize(
            '~/other/thing', '~/dotfiles', '~/tools/dotfiles-work', self.overlay_color
        )
        assert result == '~/other/thing'

    def test_main_repo_takes_precedence_over_overlay(self):
        # Pathological case: overlay path is a prefix of main repo path. The
        # main repo branch matches first, which is the right answer.
        result = self.colorize('~/dotfiles/.aliases', '~/dotfiles', '~/dot', self.overlay_color)
        assert self.repo_color in result
        assert '.aliases' in result
        assert self.overlay_color not in result

    def test_no_overlay_color_leaves_overlay_paths_uncolored(self):
        # Overlay dir set but profile couldn't be resolved → color is None.
        result = self.colorize(
            '~/tools/dotfiles-work/.gitconfig', '~/dotfiles', '~/tools/dotfiles-work', None
        )
        assert result == '~/tools/dotfiles-work/.gitconfig'


# -- register: overlay auto-targeting gated on explicit profile (3-issue fix) --


class TestRegisterOverlayProfileGating(CLITestCase):
    """register no longer auto-targets an overlay from .dotfiles_env just
    because bootstrap happened to activate one. It only routes to the
    overlay when `--overlay` is explicit, or `--profile` matches.
    """

    def setUp(self):
        super().setUp()
        self.overlay_dir = join(self.tmpdir, 'overlay')
        makedirs(self.overlay_dir)
        import yaml

        with open(join(self.overlay_dir, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump({'version': '3.0', 'profile': 'work'}, f)
        # Simulate a prior `dotfile bootstrap --overlay <overlay>` having
        # written .dotfiles_env in the fake home.
        with open(join(self.fake_home, '.dotfiles_env'), 'w') as f:
            f.write('export DOTFILES_OS=macos\n')
            f.write(f'export DOTFILES_OVERLAY="{self.overlay_dir}"\n')

    def _args(self, path, profile=None, overlay=None):
        return Namespace(
            path=path,
            category=None,
            os=None,
            profile=profile,
            name=None,
            dry_run=False,
            force=False,
            overlay=overlay,
            yes=True,
        )

    def _overlay_registry(self):
        return reg.load(join(self.overlay_dir, '__registry__.yaml'))

    def test_no_flags_targets_main_even_with_overlay_in_env(self):
        # The .dotfiles_env overlay is "sticky" from bootstrap, but register
        # without --overlay/--profile should go to main. `.zshrc` is a
        # root-dotfile convention → no registry entry in either repo;
        # verify via the file landing location instead.
        src = self.create_source_file('.zshrc')
        cmd_register(self._args(src))

        # File moved into main repo, not overlay.
        assert isfile(join(self.fake_repo, '.zshrc'))
        assert not exists(join(self.overlay_dir, '.zshrc'))
        # Source is now a symlink into main.
        assert islink(src)
        assert realpath(src) == realpath(join(self.fake_repo, '.zshrc'))

    def test_matching_profile_activates_env_overlay(self):
        # --profile work + env overlay with profile:work → register to overlay.
        # Overlay always uses the registry (convention-skip is main-repo only).
        src = self.create_source_file('.work-thing')
        cmd_register(self._args(src, profile='work'))

        main_reg = self.load_registry()
        assert len(main_reg['registered_files']) == 0
        overlay_reg = self._overlay_registry()
        assert len(overlay_reg['registered_files']) == 1
        assert overlay_reg['registered_files'][0]['profile'] == 'work'

    def test_nonmatching_profile_falls_back_to_main(self):
        # --profile home + env overlay with profile:work → register to main
        # (NOT an error; the user just isn't using the overlay for this call).
        # Because --profile is set, register uses registry mode and routes
        # to __home__/ in the main repo.
        src = self.create_source_file('.home-thing')
        cmd_register(self._args(src, profile='home'))

        # File landed in main under the profile dir; overlay registry empty.
        assert isfile(join(self.fake_repo, '__home__', '.home-thing'))
        overlay_reg = self._overlay_registry()
        assert len(overlay_reg.get('registered_files', [])) == 0
        # Main has one registry entry, profile=home.
        main_reg = self.load_registry()
        assert len(main_reg['registered_files']) == 1
        assert main_reg['registered_files'][0]['profile'] == 'home'

    def test_explicit_overlay_flag_always_honored(self):
        # --overlay is explicit user intent and wins even if --profile is absent.
        # Overlay always uses registry, so the entry ends up there.
        src = self.create_source_file('.explicit-overlay')
        cmd_register(self._args(src, overlay=self.overlay_dir))

        overlay_reg = self._overlay_registry()
        assert len(overlay_reg['registered_files']) == 1


# -- register: cross-registry conflict check --


class TestRegisterCrossRegistryConflict(CLITestCase):
    """When targeting the overlay, detect that the file is already
    registered in the main repo."""

    def setUp(self):
        super().setUp()
        self.overlay_dir = join(self.tmpdir, 'overlay')
        makedirs(self.overlay_dir)
        import yaml

        with open(join(self.overlay_dir, '__registry__.yaml'), 'w') as f:
            yaml.safe_dump({'version': '3.0', 'profile': 'work'}, f)

    def test_source_already_symlinked_blocks_re_register(self):
        # Register `.zshrc` to main (convention path — skips registry, just
        # symlinks). Re-registering via the overlay would double-manage.
        # The symlink-into-main check catches it.
        src = self.create_source_file('.zshrc', content='# main')
        self.register(src)
        # Source is now a symlink into main.
        assert islink(src)
        # Try to re-register via the overlay → blocked.
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
        with pytest.raises(SystemExit):
            cmd_register(args)

    def test_registered_in_main_blocks_overlay_register(self):
        # Registry-based registration (Library/… path, needs registry).
        # Attempting to also register in overlay should hit the cross-registry
        # conflict check.
        rel = 'Library/Application Support/Cursor/User/settings.json'
        src = self.create_source_file(rel, content='{}')
        self.register(src, category='cursor')
        # Now source is a symlink into main; try overlay register.
        args = Namespace(
            path=src,
            category='cursor',
            os=None,
            profile=None,
            name=None,
            dry_run=False,
            force=False,
            overlay=self.overlay_dir,
            yes=True,
        )
        with pytest.raises(SystemExit):
            cmd_register(args)


# -- register: placeholder-replace prompt --


class TestRegisterConventionSkipsRegistry(CLITestCase):
    """register skips the registry when the source naturally maps to a
    convention-discovered location (.config/* or root dotfile)."""

    def _raw_args(self, src, **overrides):
        # Build args WITHOUT going through CLITestCase.register (which
        # explicitly sets category to preserve legacy test behavior).
        # These tests want the real defaults.
        defaults = dict(
            path=src,
            category=None,
            os=None,
            profile=None,
            name=None,
            dry_run=False,
            force=False,
            overlay=None,
            yes=True,
        )
        defaults.update(overrides)
        return Namespace(**defaults)

    def test_root_dotfile_skips_registry(self):
        # ~/.zshrc → .zshrc in repo, no registry entry.
        src = self.create_source_file('.zshrc', content='# real shell')
        cmd_register(self._raw_args(src))

        assert len(self.load_registry()['registered_files']) == 0
        # File landed in repo; source is now a symlink.
        assert islink(src)
        assert isfile(join(self.fake_repo, '.zshrc'))

    def test_config_path_skips_registry(self):
        # ~/.config/ghostty/config → .config/ghostty/config, no registry.
        src = self.create_source_file('.config/ghostty/config', content='theme = catppuccin')
        cmd_register(self._raw_args(src))

        assert len(self.load_registry()['registered_files']) == 0
        assert islink(src)
        repo_dest = join(self.fake_repo, '.config/ghostty/config')
        assert isfile(repo_dest)

    def test_config_directory_skips_registry(self):
        # Whole .config/<tool>/ dir → directory symlink, no registry.
        src_dir = join(self.fake_home, '.config', 'ghostty')
        makedirs(src_dir)
        with open(join(src_dir, 'config'), 'w') as f:
            f.write('theme = catppuccin')
        cmd_register(self._raw_args(src_dir))

        assert len(self.load_registry()['registered_files']) == 0
        assert islink(src_dir)
        repo_dest = join(self.fake_repo, '.config/ghostty')
        assert isdir(repo_dest)

    def test_non_xdg_path_still_uses_registry(self):
        # ~/Library/Application Support/... isn't convention-discoverable →
        # must use the registry with the auto-detected category.
        rel = 'Library/Application Support/Cursor/User/settings.json'
        src = self.create_source_file(rel, content='{}')
        cmd_register(self._raw_args(src))

        reg_data = self.load_registry()
        assert len(reg_data['registered_files']) == 1
        assert reg_data['registered_files'][0]['category'] == 'cursor'

    def test_explicit_category_forces_registry(self):
        # User wants registry mode for a normally-convention path → opt in
        # via --category. The entry lands in the registry under the given
        # category, not the bare convention path.
        src = self.create_source_file('.zshrc', content='# shell')
        cmd_register(self._raw_args(src, category='shell'))

        reg_data = self.load_registry()
        assert len(reg_data['registered_files']) == 1
        entry = reg_data['registered_files'][0]
        assert entry['category'] == 'shell'
        assert entry['repo_path'] == '_shell/.zshrc'

    def test_explicit_name_forces_registry(self):
        # --name implies user wants a specific repo_path → registry mode.
        src = self.create_source_file('.bashrc', content='# bash')
        cmd_register(self._raw_args(src, name='my-bash-config'))

        reg_data = self.load_registry()
        assert len(reg_data['registered_files']) == 1
        assert reg_data['registered_files'][0]['repo_path'] == 'my-bash-config'


class TestRegisterReplacePlaceholder(CLITestCase):
    """When the repo already has a regular file at the destination (e.g.
    a starter-template placeholder) and --force isn't set, register prompts
    the user to replace it with the home version."""

    def _args(self, src):
        return Namespace(
            path=src,
            category='uncategorized',
            os=None,
            profile=None,
            name=None,
            dry_run=False,
            force=False,
            overlay=None,
            yes=False,
        )

    def _args_with_fields(self, src):
        # Pre-fill every wizard field so the register wizard doesn't fire
        # and consume our mocked inputs. The placeholder-replace prompt
        # is the only input() we want to exercise here.
        # os='' / profile='' hits the wizard's `is None` check as False
        # (explicit-empty instead of omitted), skipping those prompts.
        return Namespace(
            path=src,
            category='uncategorized',
            os='',
            profile='',
            name=None,
            dry_run=False,
            force=False,
            overlay=None,
            yes=False,
        )

    def test_interactive_yes_replaces_placeholder(self):
        # Placeholder lives in the repo at the same path register will
        # compute (category='uncategorized' → '_uncategorized/.zshrc').
        repo_dir = join(self.fake_repo, '_uncategorized')
        makedirs(repo_dir)
        repo_placeholder = join(repo_dir, '.zshrc')
        with open(repo_placeholder, 'w') as f:
            f.write('# placeholder — replace me\n')

        src = self.create_source_file('.zshrc', content='# real content\n')

        # First prompt: replace-placeholder → 'y'; second: final "Proceed?" → 'y'.
        from unittest.mock import patch as mock_patch

        with (
            mock_patch('sys.stdin.isatty', return_value=True),
            mock_patch('builtins.input', side_effect=['y', 'y']),
        ):
            cmd_register(self._args_with_fields(src))

        assert islink(src)
        with open(src) as f:
            assert 'real content' in f.read()
        with open(repo_placeholder) as f:
            assert 'real content' in f.read()

    def test_interactive_no_bails(self):
        repo_dir = join(self.fake_repo, '_uncategorized')
        makedirs(repo_dir)
        repo_placeholder = join(repo_dir, '.zshrc')
        with open(repo_placeholder, 'w') as f:
            f.write('# placeholder\n')
        src = self.create_source_file('.zshrc', content='# home\n')

        from unittest.mock import patch as mock_patch

        with (
            mock_patch('sys.stdin.isatty', return_value=True),
            mock_patch('builtins.input', return_value='n'),
            pytest.raises(SystemExit),
        ):
            cmd_register(self._args_with_fields(src))

        # Source file untouched; placeholder unchanged.
        assert isfile(src) and not islink(src)
        with open(repo_placeholder) as f:
            assert 'placeholder' in f.read()

    def test_non_interactive_without_force_errors(self):
        # CI / piped invocation path: no tty, no --force → still errors,
        # don't silently overwrite checked-in content.
        repo_dir = join(self.fake_repo, '_uncategorized')
        makedirs(repo_dir)
        repo_placeholder = join(repo_dir, '.zshrc')
        with open(repo_placeholder, 'w') as f:
            f.write('# placeholder\n')
        src = self.create_source_file('.zshrc', content='# home\n')

        with pytest.raises(SystemExit):
            cmd_register(self._args(src))


if __name__ == '__main__':
    unittest.main()
