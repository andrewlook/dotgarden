#!/usr/bin/env bash
# Overlay profile metadata is mandatory.
# - Missing __registry__.yaml                 → bootstrap aborts
# - Registry without `profile: <name>` field  → bootstrap aborts
# - --profile mismatching overlay's profile   → bootstrap aborts
# - --profile matching / omitted               → ok

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

copy_fixture_to_repo "$(dirname "$0")/../../tests/fixtures/minimal"

# ---- Case 1: overlay with no __registry__.yaml ----
overlay_no_reg="$TEST_TMPDIR/overlay-no-reg"
mkdir -p "$overlay_no_reg"
echo "# bare file" > "$overlay_no_reg/.gitconfig"

assert_exit_nonzero "overlay without __registry__.yaml → abort" \
    dotfile bootstrap --os linux --profile work --overlay "$overlay_no_reg"

# ---- Case 2: overlay with __registry__.yaml but no profile: field ----
overlay_no_profile="$TEST_TMPDIR/overlay-no-profile"
mkdir -p "$overlay_no_profile"
cat > "$overlay_no_profile/__registry__.yaml" <<'EOF'
version: '3.0'
EOF
echo "# bare file" > "$overlay_no_profile/.gitconfig"

assert_exit_nonzero "overlay without profile: field → abort" \
    dotfile bootstrap --os linux --profile work --overlay "$overlay_no_profile"

# ---- Case 3: --profile mismatches the overlay's declared profile ----
overlay_work="$TEST_TMPDIR/overlay-work"
mkdir -p "$overlay_work"
cat > "$overlay_work/__registry__.yaml" <<'EOF'
version: '3.0'
profile: work
EOF
echo "# bare file" > "$overlay_work/.gitconfig"

assert_exit_nonzero "overlay declares profile:work but --profile home → abort" \
    dotfile bootstrap --os linux --profile home --overlay "$overlay_work"

# ---- Case 4: --profile matches overlay → ok ----
assert_exit_zero "overlay declares profile:work and --profile work → ok" \
    dotfile bootstrap --os linux --profile work --overlay "$overlay_work"

# ---- Case 5: --profile omitted → inferred from overlay → ok ----
# Reset the home for a clean run
rm -f "$TEST_HOME/.dotfiles_env" "$TEST_HOME/.work.gitconfig"

assert_exit_zero "overlay declares profile:work, --profile omitted → inferred" \
    dotfile bootstrap --os linux --overlay "$overlay_work"

# Verify the overlay content was actually linked with the work-profile prefix,
# proving profile inference happened.
assert_symlink_to "$TEST_HOME/.work.gitconfig" "$overlay_work/.gitconfig"
