#!/usr/bin/env bash
# Registers a user config into the repo (creating a symlink back to $HOME),
# then unregisters with --restore (default) and verifies the original content
# is restored.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

# Repo is empty — register will create the first entry.
mkdir -p "$TEST_HOME/.config/myapp"
cat > "$TEST_HOME/.config/myapp/settings.json" <<'EOF'
{"theme": "nord", "fontSize": 14}
EOF

# --- register ---
# `dotfile register` prompts "Proceed? [y/N]:" by default. Pipe confirmation.
if ! printf 'y\n' | dotfile register "$TEST_HOME/.config/myapp/settings.json" \
        > /tmp/reg.$$ 2>&1; then
    _fail "register failed" "$(cat /tmp/reg.$$)"
fi
rm -f /tmp/reg.$$
_pass "register succeeded"

# The original path should now be a symlink pointing into the repo.
assert_symlink "$TEST_HOME/.config/myapp/settings.json"
target=$(readlink "$TEST_HOME/.config/myapp/settings.json")
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
if ! printf 'y\n' | dotfile unregister "$TEST_HOME/.config/myapp/settings.json" \
        > /tmp/unreg.$$ 2>&1; then
    _fail "unregister failed" "$(cat /tmp/unreg.$$)"
fi
rm -f /tmp/unreg.$$
_pass "unregister succeeded"

# After unregister --restore (default): original path is a regular file
# with the original content, repo copy is gone.
assert_regular_file "$TEST_HOME/.config/myapp/settings.json"
assert_file_contains "$TEST_HOME/.config/myapp/settings.json" '"theme": "nord"'
assert_not_exists "$TEST_REPO/_myapp/settings.json"
