#!/usr/bin/env bash
# Verifies that an overlay containing a bare .config/<tool>/<base> file
# (no profile modifier) is rejected at bootstrap time with a clear error.

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

# Overlay with BARE config.fish (should be rejected).
TEST_OVERLAY="$TEST_TMPDIR/overlay"
mkdir -p "$TEST_OVERLAY/.config/fish"
cat > "$TEST_OVERLAY/__registry__.yaml" <<EOF
version: '3.0'
profile: work
EOF
echo "# overlay base fish (ILLEGAL — must be config.work.fish)" > "$TEST_OVERLAY/.config/fish/config.fish"

assert_exit_nonzero "bootstrap rejects bare overlay .config file" \
    dotfile bootstrap --os linux --profile work --overlay "$TEST_OVERLAY"
