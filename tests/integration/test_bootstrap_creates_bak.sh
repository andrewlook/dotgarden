#!/usr/bin/env bash
# Verifies that bootstrap backs up a pre-existing regular file at a target
# path to <target>.bak before creating the symlink.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

copy_fixture_to_repo "$(dirname "$0")/../../examples/minimal"

# Pre-place a regular file at ~/.gitconfig with identifiable content.
echo '# PRE-EXISTING USER CONTENT' > "$TEST_HOME/.gitconfig"
assert_regular_file "$TEST_HOME/.gitconfig"

assert_exit_zero "bootstrap (conflict with regular file)" \
    dotfile bootstrap --os linux

# After bootstrap: .gitconfig is now a symlink, old content preserved in .bak
assert_symlink_to "$TEST_HOME/.gitconfig"      "$TEST_REPO/.gitconfig"
assert_regular_file "$TEST_HOME/.gitconfig.bak"
assert_file_contains "$TEST_HOME/.gitconfig.bak" "PRE-EXISTING USER CONTENT"
