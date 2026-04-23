#!/usr/bin/env bash
# Verifies Unit 5: bootstrap fails non-interactively when a base has
# variants but no known include syntax, and --skip-unsupported lets it
# proceed with a warning.

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

# Zed has .json configs — not in LOCAL_TOOL_TYPES, no include syntax.
mkdir -p "$TEST_REPO/.config/zed"
echo '{}'                    > "$TEST_REPO/.config/zed/settings.json"
echo '{"font_size": 14}'     > "$TEST_REPO/.config/zed/settings.linux.json"

# Part 1: default non-interactive → fail
assert_exit_nonzero "bootstrap fails non-interactively on unsupported variant" \
    dotfile bootstrap --os linux

# Part 2: --skip-unsupported → success with warning
assert_exit_zero "bootstrap --skip-unsupported proceeds" \
    dotfile bootstrap --os linux --skip-unsupported

# No .local was generated for the unsupported base.
assert_not_exists "$TEST_HOME/.config/zed/settings.json.local"
assert_not_exists "$TEST_REPO/.config/zed/settings.json.local"

# The bootstrap still symlinked the directory.
assert_symlink_to "$TEST_HOME/.config/zed" "$TEST_REPO/.config/zed"
