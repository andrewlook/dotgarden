#!/usr/bin/env bash
# Verifies `dotfile specialize os .config/fish/config.fish` creates
# nested variant files, appends the fish include line to the base,
# and a subsequent `dotfile bootstrap` produces a working .local.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

cat > "$TEST_REPO/__registry__.yaml" <<EOF
version: '3.0'
os:
  - macos
  - linux
profiles:
  - work
  - home
EOF

mkdir -p "$TEST_REPO/.config/fish"
cat > "$TEST_REPO/.config/fish/config.fish" <<'EOF'
set -gx EDITOR nvim
EOF

assert_exit_zero "specialize nested fish by os" \
    dotfile specialize os .config/fish/config.fish

# Variant files created inside .config/fish/
[ -f "$TEST_REPO/.config/fish/config.macos.fish" ] \
    || _fail "expected .config/fish/config.macos.fish" "$(ls "$TEST_REPO/.config/fish")"
_pass "created .config/fish/config.macos.fish"

[ -f "$TEST_REPO/.config/fish/config.linux.fish" ] \
    || _fail "expected .config/fish/config.linux.fish" "$(ls "$TEST_REPO/.config/fish")"
_pass "created .config/fish/config.linux.fish"

# Base file got the fish include appended.
assert_file_contains "$TEST_REPO/.config/fish/config.fish" \
    "test -e ~/.config/fish/config.fish.local"
assert_file_contains "$TEST_REPO/.config/fish/config.fish" \
    "and source ~/.config/fish/config.fish.local"

# Idempotent — re-running should not duplicate the include line.
assert_exit_zero "re-specialize is idempotent" \
    dotfile specialize os .config/fish/config.fish
count=$(grep -c "config.fish.local" "$TEST_REPO/.config/fish/config.fish")
[ "$count" -eq 1 ] \
    || _fail "expected 1 include line, got $count" \
             "$(cat "$TEST_REPO/.config/fish/config.fish")"
_pass "include line not duplicated on re-run"

# Now bootstrap generates .local referencing the right variant for this OS.
assert_exit_zero "bootstrap after specialize" \
    dotfile bootstrap --os linux

LOCAL="$TEST_REPO/.config/fish/config.fish.local"
assert_file_contains "$LOCAL" "config.linux.fish"
assert_file_not_contains "$LOCAL" "config.macos.fish"
