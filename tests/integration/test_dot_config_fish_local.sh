#!/usr/bin/env bash
# Verifies fish .local generation with nested variants: config.fish +
# config.linux.fish in the repo → ~/.config/fish/config.fish.local with
# fish-syntax include lines.

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
# fish base config
test -e ~/.config/fish/config.fish.local; and source ~/.config/fish/config.fish.local
EOF
echo "# linux-specific" > "$TEST_REPO/.config/fish/config.linux.fish"
echo "# macos-specific" > "$TEST_REPO/.config/fish/config.macos.fish"
echo "# work-specific"  > "$TEST_REPO/.config/fish/config.work.fish"

assert_exit_zero "bootstrap linux/work" \
    dotfile bootstrap --os linux --profile work

# Directory symlink created.
assert_symlink_to "$TEST_HOME/.config/fish" "$TEST_REPO/.config/fish"

# .local file lives next to the base (via the directory symlink).
REPO_LOCAL="$TEST_REPO/.config/fish/config.fish.local"
assert_regular_file "$REPO_LOCAL"
assert_file_contains "$REPO_LOCAL" "test -e ~/.config/fish/config.linux.fish"
assert_file_contains "$REPO_LOCAL" "and source ~/.config/fish/config.linux.fish"
assert_file_contains "$REPO_LOCAL" "test -e ~/.config/fish/config.work.fish"
# Wrong-OS variant must NOT be referenced.
assert_file_not_contains "$REPO_LOCAL" "config.macos.fish"
# Reachable through the home symlink too.
assert_file_contains "$TEST_HOME/.config/fish/config.fish.local" "config.linux.fish"

# Idempotent: second run should leave everything green and report 'ok' for
# the already-present .local.
run_capture /tmp/boot2.$$ dotfile bootstrap --os linux --profile work
grep -q "ok" /tmp/boot2.$$ || _fail "expected 'ok' marker from idempotent run" "$(cat /tmp/boot2.$$)"
rm -f /tmp/boot2.$$
_pass "second bootstrap reports 'ok' for existing .local"
