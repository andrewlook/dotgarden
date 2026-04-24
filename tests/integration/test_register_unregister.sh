#!/usr/bin/env bash
# Registers a user config into the repo (creating a symlink back to $HOME),
# then unregisters with --restore (default) and verifies the original content
# is restored.
#
# Uses a non-convention path (`~/Library/...`) so register goes through the
# registry path. Convention-eligible paths (e.g. ~/.config/*) skip the
# registry entirely and are covered by test_dot_config_convention.sh.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

# Repo is empty — register will create the first entry.
mkdir -p "$TEST_HOME/Library/Application Support/myapp"
SRC="$TEST_HOME/Library/Application Support/myapp/settings.json"
cat > "$SRC" <<'EOF'
{"theme": "nord", "fontSize": 14}
EOF

# --- register ---
# `dotfile register` prompts "Proceed? [y/N]:" by default. Pipe confirmation.
if ! printf 'y\n' | dotfile register "$SRC" \
        > /tmp/reg.$$ 2>&1; then
    _fail "register failed" "$(cat /tmp/reg.$$)"
fi
rm -f /tmp/reg.$$
_pass "register succeeded"

# The original path should now be a symlink pointing into the repo.
assert_symlink "$SRC"
target=$(readlink "$SRC")
case "$target" in
    "$TEST_REPO"/*) _pass "symlink resolves into \$DOTFILES: $target" ;;
    *) _fail "symlink does not resolve into repo: $target" ;;
esac

# Repo copy exists and has the original content.
assert_file_contains "$target" '"theme": "nord"'

# Registry recorded the entry.
assert_file_contains "$TEST_REPO/__registry__.yaml" "settings.json"

# `dotfile list` should surface it.
run_capture /tmp/dotfile-list.$$ dotfile list
assert_file_contains /tmp/dotfile-list.$$ "settings.json"
rm -f /tmp/dotfile-list.$$

# --- unregister (default: restore) ---
# `dotfile unregister` also prompts for confirmation.
if ! printf 'y\n' | dotfile unregister "$SRC" \
        > /tmp/unreg.$$ 2>&1; then
    _fail "unregister failed" "$(cat /tmp/unreg.$$)"
fi
rm -f /tmp/unreg.$$
_pass "unregister succeeded"

# After unregister --restore (default): original path is a regular file
# with the original content, repo copy is gone.
assert_regular_file "$SRC"
assert_file_contains "$SRC" '"theme": "nord"'
