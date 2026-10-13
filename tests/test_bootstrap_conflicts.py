"""Bootstrap must preserve unmanaged destinations and every older backup."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from dotgarden.symlinks import bootstrap, prepare_symlink_target


@pytest.fixture
def layout(tmp_path):
    repo = tmp_path / 'repo'
    home = tmp_path / 'home'
    repo.mkdir()
    home.mkdir()
    (repo / '.zshrc').write_text('# managed zshrc\n')
    (repo / '.zprofile').write_text('# managed zprofile\n')
    return repo, home


def test_conflict_aborts_before_any_changes(layout):
    repo, home = layout
    (home / '.zshrc').write_text('# personal commands\n')

    with pytest.raises(RuntimeError, match='--force'):
        bootstrap(str(repo), str(home), 'macos')

    assert (home / '.zshrc').read_text() == '# personal commands\n'
    assert sorted(path.name for path in home.iterdir()) == ['.zshrc']


def test_force_keeps_existing_backup_and_is_idempotent(layout):
    repo, home = layout
    (home / '.zshrc').write_text('new personal settings')
    (home / '.zshrc.bak').write_text('original personal settings')

    bootstrap(str(repo), str(home), 'macos', force=True)
    bootstrap(str(repo), str(home), 'macos')

    assert (home / '.zshrc').is_symlink()
    assert (home / '.zshrc').resolve() == repo / '.zshrc'
    assert (home / '.zshrc.bak').read_text() == 'original personal settings'
    assert (home / '.zshrc.bak.1').read_text() == 'new personal settings'
    assert not (home / '.zshrc.bak.2').exists()


def test_unrelated_live_symlink_requires_force(layout, tmp_path):
    repo, home = layout
    other = tmp_path / 'other-settings'
    other.write_text('outside config')
    (home / '.zshrc').symlink_to(other)

    with pytest.raises(RuntimeError, match='unmanaged'):
        bootstrap(str(repo), str(home), 'macos')
    assert (home / '.zshrc').resolve() == other

    bootstrap(str(repo), str(home), 'macos', force=True)
    assert (home / '.zshrc.bak').is_symlink()
    assert (home / '.zshrc.bak').resolve() == other
    assert other.read_text() == 'outside config'


def test_managed_symlink_can_change_targets(layout):
    repo, home = layout
    (repo / 'profiles').mkdir()
    old = repo / 'profiles' / 'previous-zshrc'
    old.write_text('previous managed config')
    (home / '.zshrc').symlink_to(old)

    bootstrap(str(repo), str(home), 'macos')

    assert (home / '.zshrc').resolve() == repo / '.zshrc'
    assert old.read_text() == 'previous managed config'


def test_relative_correct_symlink_is_unchanged(layout):
    repo, home = layout
    link = home / '.zshrc'
    link.symlink_to('../repo/.zshrc')

    assert prepare_symlink_target(str(repo / '.zshrc'), str(link)) == 'ok'
    bootstrap(str(repo), str(home), 'macos')

    assert link.readlink() == Path('../repo/.zshrc')
    assert not (home / '.zshrc.bak').exists()


def test_broken_backup_name_is_not_reused(layout):
    repo, home = layout
    link = home / '.zshrc'
    link.write_text('keep me')
    backup = home / '.zshrc.bak'
    backup.symlink_to('missing-original')

    prepare_symlink_target(str(repo / '.zshrc'), str(link))

    assert backup.is_symlink()
    assert backup.readlink() == Path('missing-original')
    assert (home / '.zshrc.bak.1').read_text() == 'keep me'


def test_directory_symlink_backup_preserves_link_and_target(tmp_path):
    target = tmp_path / 'managed'
    original = tmp_path / 'original'
    target.mkdir()
    original.mkdir()
    (original / 'custom').write_text('keep directory content')
    link = tmp_path / 'config'
    link.symlink_to(original, target_is_directory=True)

    assert prepare_symlink_target(str(target), str(link)) == 'replaced'
    assert (tmp_path / 'config.bak').is_symlink()
    assert (tmp_path / 'config.bak').resolve() == original
    assert (original / 'custom').read_text() == 'keep directory content'


def test_cli_refuses_conflict_then_force_preserves_contents(layout):
    repo, home = layout
    (home / '.zshrc').write_text('actual personal config')
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(('DOTFILES', 'DOTFILE_'))
    }
    environment.update(HOME=str(home), DOTFILE_HOME=str(home), DOTFILES=str(repo))
    command = [
        sys.executable,
        '-c',
        'from dotgarden.cli import main; main()',
        'bootstrap',
        '--os',
        'macos',
    ]
    refused = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    assert refused.returncode != 0
    assert '--force' in refused.stderr
    assert (home / '.zshrc').read_text() == 'actual personal config'
    assert not (home / '.zprofile').exists()

    forced = subprocess.run(
        [*command, '--force'], env=environment, capture_output=True, text=True, check=False
    )
    assert forced.returncode == 0, forced.stderr
    assert (home / '.zshrc').resolve() == repo / '.zshrc'
    assert (home / '.zshrc.bak').read_text() == 'actual personal config'
