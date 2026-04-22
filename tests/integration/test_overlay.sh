#!/usr/bin/env bash
# Overlay support: a second dir can layer in profile-scoped dotfiles.
# Under the "overlay = one implicit profile" model:
#   - the overlay declares its profile ONCE in __registry__.yaml
#   - overlay files are BARE (no profile prefix in the filename)
#   - bootstrap renames them to .<profile>.<basename> at link time

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

# Main repo = examples/minimal (has .gitconfig and .zprofile)
copy_fixture_to_repo "$(dirname "$0")/../../examples/minimal"

# Overlay dir with declared profile + bare-named files
overlay_dir="$TEST_TMPDIR/overlay"
mkdir -p "$overlay_dir"
cat > "$overlay_dir/__registry__.yaml" <<'EOF'
version: '3.0'
profile: work
EOF
cat > "$overlay_dir/.gitconfig" <<'EOF'
[user]
    email = work@example.com
EOF
cat > "$overlay_dir/.zprofile" <<'EOF'
# overlay's zprofile, applied only for profile=work
EOF

assert_exit_zero "bootstrap with overlay" \
    dotfile bootstrap --os linux --profile work --overlay "$overlay_dir"

# Overlay's bare files are renamed to the profile-prefixed name in HOME
assert_symlink_to "$TEST_HOME/.work.gitconfig" "$overlay_dir/.gitconfig"
assert_symlink_to "$TEST_HOME/.work.zprofile"  "$overlay_dir/.zprofile"

# Main file is untouched — coexists with the overlay file
assert_symlink_to "$TEST_HOME/.gitconfig" "$TEST_REPO/.gitconfig"

# .dotfiles_env records the overlay
assert_file_contains "$TEST_HOME/.dotfiles_env" "DOTFILES_OVERLAY=$overlay_dir"

# .gitconfig.local includes the overlay's profile-prefixed variant
assert_file_contains "$TEST_HOME/.gitconfig.local" ".work.gitconfig"

# Bad overlay path should abort with non-zero exit.
assert_exit_nonzero "bootstrap with nonexistent overlay" \
    dotfile bootstrap --os linux --overlay "$TEST_TMPDIR/does-not-exist"
