#!/usr/bin/env bash
# `dotfile register --overlay <dir>` routes the new registration into the
# overlay repo instead of the main dotfiles repo. End-to-end verification:
# the file is moved to the overlay dir, the overlay's __registry__.yaml
# gets the entry, and main's __registry__.yaml is untouched.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

# Main repo starts empty (no pre-existing registry).
mkdir -p "$TEST_HOME/.config/myapp"
cat > "$TEST_HOME/.config/myapp/settings.json" <<'EOF'
{"theme": "nord"}
EOF

# Overlay with declared profile.
overlay_dir="$TEST_TMPDIR/overlay-work"
mkdir -p "$overlay_dir"
cat > "$overlay_dir/__registry__.yaml" <<'EOF'
version: '3.0'
profile: work
EOF

# Register via --overlay, auto-confirmed with --yes.
assert_exit_zero "register --overlay --yes" \
    dotfile register --overlay "$overlay_dir" --yes \
        "$TEST_HOME/.config/myapp/settings.json"

# Source path is now a symlink pointing into the overlay dir.
assert_symlink "$TEST_HOME/.config/myapp/settings.json"
target=$(readlink "$TEST_HOME/.config/myapp/settings.json")
case "$target" in
    "$overlay_dir"/*) _pass "symlink resolves into overlay: $target" ;;
    *) _fail "symlink should point into overlay, got: $target" ;;
esac

# Overlay's __registry__.yaml lists the new entry AND preserves `profile: work`.
assert_file_contains "$overlay_dir/__registry__.yaml" "settings.json"
assert_file_contains "$overlay_dir/__registry__.yaml" "profile: work"

# Main repo's registry (if it exists) has nothing new.
if [ -f "$TEST_REPO/__registry__.yaml" ]; then
    assert_file_not_contains "$TEST_REPO/__registry__.yaml" "settings.json"
fi

# --profile mismatch is rejected.
mkdir -p "$TEST_HOME/.config/other"
echo 'other' > "$TEST_HOME/.config/other/settings.json"
assert_exit_nonzero "register --overlay --profile mismatch → abort" \
    dotfile register --overlay "$overlay_dir" --profile home --yes \
        "$TEST_HOME/.config/other/settings.json"

# Mismatch should NOT have moved the file.
assert_regular_file "$TEST_HOME/.config/other/settings.json"
