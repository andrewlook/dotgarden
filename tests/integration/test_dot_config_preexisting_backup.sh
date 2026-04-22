#!/usr/bin/env bash
# Verifies that pre-existing ~/.config/<tool>/ directories with user content
# are backed up to .bak before being replaced by the convention symlink.
# Load-bearing for devbox and boxes where fish/etc already wrote default files.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

cat > "$TEST_REPO/__registry__.yaml" << EOF
version: '3.0'
os:
  - macos
  - linux
profiles:
  - work
  - home
EOF

mkdir -p "$TEST_REPO/.config/fish"
echo "# repo config" > "$TEST_REPO/.config/fish/config.fish"

# Simulate fish having run on first login: ~/.config/fish/ exists with user content.
mkdir -p "$TEST_HOME/.config/fish"
echo "# user left behind" > "$TEST_HOME/.config/fish/fish_variables"
echo "# user config" > "$TEST_HOME/.config/fish/config.fish"

assert_exit_zero "bootstrap with pre-existing ~/.config/fish" \
    dotfile bootstrap --os linux

# The home directory is now a symlink to the repo.
assert_symlink_to "$TEST_HOME/.config/fish" "$TEST_REPO/.config/fish"
assert_file_contains "$TEST_HOME/.config/fish/config.fish" "repo config"

# Pre-existing content is backed up to a .bak neighbour.
BAK="$TEST_HOME/.config/fish.bak"
[ -d "$BAK" ] || _fail "expected backup at $BAK" "$(ls -la "$TEST_HOME/.config")"
_pass "pre-existing ~/.config/fish backed up to $BAK"

assert_file_contains "$BAK/config.fish" "user config"
assert_file_contains "$BAK/fish_variables" "user left behind"
