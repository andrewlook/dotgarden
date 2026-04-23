#!/usr/bin/env bash
# Bootstraps tests/fixtures/full/ as --os linux --profile work and verifies
# variant filtering and .local generation.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

copy_fixture_to_repo "$(dirname "$0")/../../tests/fixtures/full"

assert_exit_zero "bootstrap linux/work" \
    dotfile bootstrap --os linux --profile work

# Common dotfiles — linked
assert_symlink_to "$TEST_HOME/.gitconfig"  "$TEST_REPO/.gitconfig"
assert_symlink_to "$TEST_HOME/.tmux.conf"  "$TEST_REPO/.tmux.conf"
assert_symlink_to "$TEST_HOME/.zprofile"   "$TEST_REPO/.zprofile"

# Linux OS variants — linked
assert_symlink_to "$TEST_HOME/.linux.zprofile"  "$TEST_REPO/.linux.zprofile"
assert_symlink_to "$TEST_HOME/.linux.tmux.conf" "$TEST_REPO/.linux.tmux.conf"

# Work profile variant — linked
assert_symlink_to "$TEST_HOME/.work.gitconfig" "$TEST_REPO/.work.gitconfig"

# Wrong-OS and wrong-profile variants — NOT linked
assert_not_exists "$TEST_HOME/.macos.zprofile"
assert_not_exists "$TEST_HOME/.macos.tmux.conf"
assert_not_exists "$TEST_HOME/.home.gitconfig"

# .local files — generated with the right includes
assert_file_contains "$TEST_HOME/.zprofile.local"  ".linux.zprofile"
assert_file_not_contains "$TEST_HOME/.zprofile.local"  ".macos.zprofile"

assert_file_contains "$TEST_HOME/.tmux.conf.local"  ".linux.tmux.conf"
assert_file_not_contains "$TEST_HOME/.tmux.conf.local"  ".macos.tmux.conf"

assert_file_contains "$TEST_HOME/.gitconfig.local"  ".work.gitconfig"
assert_file_not_contains "$TEST_HOME/.gitconfig.local"  ".home.gitconfig"

# .dotfiles_env recorded OS and profile
assert_file_contains "$TEST_HOME/.dotfiles_env"  "export DOTFILES_OS=linux"
assert_file_contains "$TEST_HOME/.dotfiles_env"  "export DOTFILES_PROFILE=work"
