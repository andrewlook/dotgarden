"""Tests for lib.paths module."""

import os
import shutil
import tempfile
import unittest

import pytest

from dotgarden.paths import (
    auto_detect_category,
    escape_spaces,
    format_for_display,
    generate_id,
    validate,
)


class TestValidate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.fake_repo = os.path.join(self.tmpdir, 'dotfiles')
        os.makedirs(self.fake_repo)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_returns_absolute_path(self):
        f = os.path.join(self.tmpdir, 'testfile')
        open(f, 'w').close()
        result = validate(f, self.fake_repo)
        self.assertTrue(os.path.isabs(result))

    def test_raises_on_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            validate('/nonexistent/path', self.fake_repo)

    def test_allows_missing_when_must_exist_false(self):
        result = validate('/nonexistent/path', self.fake_repo, must_exist=False)
        self.assertEqual(result, '/nonexistent/path')

    def test_rejects_path_inside_repo(self):
        f = os.path.join(self.fake_repo, 'inside')
        open(f, 'w').close()
        with self.assertRaises(ValueError):
            validate(f, self.fake_repo)


# -- Table-driven: generate_id --

GENERATE_ID_CASES = [
    # (source_path,             category,  expected)
    ('/path/to/settings.json', 'vscode', 'vscode-settings'),
    ('/path/to/keymap.json', 'zed', 'zed-keymap'),
    ('/home/user/.bashrc', None, 'bashrc'),
    ('/home/user/.zshrc', None, 'zshrc'),
    ('/path/My File (copy).json', 'cat', 'cat-my-file-copy'),
]


@pytest.mark.parametrize(
    'source_path,category,expected', GENERATE_ID_CASES, ids=[c[2] for c in GENERATE_ID_CASES]
)
def test_generate_id(source_path, category, expected):
    assert generate_id(source_path, category) == expected


# -- Table-driven: format_for_display --

FORMAT_DISPLAY_CASES = [
    # (path,                  home_dir,      expected)
    ('/home/user/.bashrc', '/home/user', '~/.bashrc'),
    ('/home/user/a/b', '/home/user', '~/a/b'),
    ('/etc/config', '/home/user', '/etc/config'),
    ('/other/path', '/home/user', '/other/path'),
]


@pytest.mark.parametrize('path,home_dir,expected', FORMAT_DISPLAY_CASES)
def test_format_for_display(path, home_dir, expected):
    assert format_for_display(path, home_dir) == expected


# -- Table-driven: escape_spaces --

ESCAPE_SPACES_CASES = [
    ('~/foo/bar', '~/foo/bar'),
    ('~/Library/Application Support', '~/Library/Application\\ Support'),
    ('~/a b/c d/e', '~/a\\ b/c\\ d/e'),
    ('/no-spaces', '/no-spaces'),
]


@pytest.mark.parametrize('path,expected', ESCAPE_SPACES_CASES)
def test_escape_spaces(path, expected):
    assert escape_spaces(path) == expected


# -- Table-driven: auto_detect_category --

HOME = '/home/user'

AUTO_DETECT_CASES = [
    # (source_path,                                                            expected)
    (f'{HOME}/Library/Application Support/Code/User/settings.json', 'vscode'),
    (f'{HOME}/Library/Application Support/Code/User/keybindings.json', 'vscode'),
    (f'{HOME}/Library/Application Support/Cursor/User/settings.json', 'cursor'),
    (f'{HOME}/Library/Application Support/Cursor/User/keybindings.json', 'cursor'),
    (f'{HOME}/.config/nvim/init.lua', 'nvim'),
    (f'{HOME}/.config/zed/settings.json', 'zed'),
    (f'{HOME}/.config/ghostty/config', 'ghostty'),
    (f'{HOME}/.bashrc', None),
    (f'{HOME}/.zshrc', None),
    (f'{HOME}/some/nested/config', 'common'),
]


@pytest.mark.parametrize(
    'source_path,expected', AUTO_DETECT_CASES, ids=[c[1] or 'home-dir' for c in AUTO_DETECT_CASES]
)
def test_auto_detect_category(source_path, expected):
    assert auto_detect_category(source_path, HOME) == expected


if __name__ == '__main__':
    unittest.main()
