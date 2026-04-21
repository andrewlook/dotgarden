#!/usr/bin/env bash
# DOTFILE_HOME redirects every path the CLI touches to a fake home, so you
# can exercise bootstrap/register/unregister from a worktree without mutating
# your real dotfiles.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

copy_fixture_to_repo "$(dirname "$0")/../../examples/minimal"

# Make a THIRD directory — the "fake home" the user wants bootstrap to target.
# $TEST_HOME is what HOME currently is; we deliberately want bootstrap to
# write to somewhere else.
fake_home="$TEST_TMPDIR/fake-home"
mkdir -p "$fake_home"

# Sanity: before bootstrap, neither HOME nor fake_home has any symlinks.
assert_not_exists "$TEST_HOME/.gitconfig"
assert_not_exists "$fake_home/.gitconfig"

# Bootstrap with DOTFILE_HOME pointing at fake_home.
DOTFILE_HOME="$fake_home" dotfile bootstrap --os linux > /tmp/dfh-bootstrap.$$ 2>&1 \
    || { cat /tmp/dfh-bootstrap.$$; _fail "bootstrap with DOTFILE_HOME failed"; }
grep -q 'DOTFILE_HOME' /tmp/dfh-bootstrap.$$ \
    || _fail "bootstrap did not announce the DOTFILE_HOME redirection" "$(cat /tmp/dfh-bootstrap.$$)"
_pass "bootstrap announced DOTFILE_HOME redirection"
rm -f /tmp/dfh-bootstrap.$$

# Symlinks went to fake_home, not the real HOME.
assert_symlink_to "$fake_home/.gitconfig" "$TEST_REPO/.gitconfig"
assert_symlink_to "$fake_home/.zprofile"  "$TEST_REPO/.zprofile"

# Real HOME is untouched.
assert_not_exists "$TEST_HOME/.gitconfig"
assert_not_exists "$TEST_HOME/.zprofile"
assert_not_exists "$TEST_HOME/.dotfiles_env"

# .dotfiles_env lives in the fake home.
assert_file_contains "$fake_home/.dotfiles_env" "export DOTFILES_OS=linux"

# status also honors DOTFILE_HOME — it should read the fake home and report clean.
DOTFILE_HOME="$fake_home" dotfile status > /tmp/dfh-status.$$ 2>&1 \
    || { cat /tmp/dfh-status.$$; _fail "status with DOTFILE_HOME failed"; }
assert_file_contains /tmp/dfh-status.$$ "healthy"
rm -f /tmp/dfh-status.$$

# Missing DOTFILE_HOME path aborts with non-zero.
assert_exit_nonzero "DOTFILE_HOME=missing aborts" \
    env DOTFILE_HOME="$TEST_TMPDIR/does-not-exist" dotfile bootstrap --os linux
