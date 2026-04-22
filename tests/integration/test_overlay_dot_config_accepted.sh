#!/usr/bin/env bash
# Verifies overlay .config/<tool>/ files with pre-named variants are
# accepted and referenced (by absolute path) in the main repo's .local.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

# Main repo.
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
echo "# main fish" > "$TEST_REPO/.config/fish/config.fish"

# Overlay — distinct directory with profile declared.
TEST_OVERLAY="$TEST_TMPDIR/overlay"
mkdir -p "$TEST_OVERLAY/.config/fish"
cat > "$TEST_OVERLAY/__registry__.yaml" <<EOF
version: '3.0'
profile: work
EOF
echo "# overlay work fish" > "$TEST_OVERLAY/.config/fish/config.work.fish"

assert_exit_zero "bootstrap linux/work with overlay" \
    dotfile bootstrap --os linux --profile work --overlay "$TEST_OVERLAY"

# Main dir symlinked through.
assert_symlink_to "$TEST_HOME/.config/fish" "$TEST_REPO/.config/fish"

# .local file includes the overlay file by absolute path.
LOCAL="$TEST_REPO/.config/fish/config.fish.local"
assert_regular_file "$LOCAL"
assert_file_contains "$LOCAL" "$TEST_OVERLAY/.config/fish/config.work.fish"

# No file-level symlink for the overlay variant — it's referenced by path,
# not copied into the main repo's dir.
assert_not_exists "$TEST_REPO/.config/fish/config.work.fish"
