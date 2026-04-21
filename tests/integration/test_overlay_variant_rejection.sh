#!/usr/bin/env bash
# OS variants inside an overlay are not supported in v1.
# An overlay file named .macos.zprofile should be rejected with a clear error.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

copy_fixture_to_repo "$(dirname "$0")/../../examples/minimal"

overlay_dir="$TEST_TMPDIR/overlay"
mkdir -p "$overlay_dir"
cat > "$overlay_dir/__registry__.yaml" <<'EOF'
version: '3.0'
profile: work
EOF
# OS-prefixed filename — not allowed in v1 overlays.
echo "# macos-only in overlay" > "$overlay_dir/.macos.zprofile"

rc=0
dotfile bootstrap --os macos --overlay "$overlay_dir" > /tmp/variant-reject.$$ 2>&1 || rc=$?

if [ "$rc" -eq 0 ]; then
    _fail "bootstrap should have rejected .macos.zprofile in overlay" \
        "$(cat /tmp/variant-reject.$$)"
fi

grep -qE '\.macos\.zprofile' /tmp/variant-reject.$$ \
    || _fail "error message should name the offending file" "$(cat /tmp/variant-reject.$$)"
grep -qiE 'overlay|OS' /tmp/variant-reject.$$ \
    || _fail "error message should explain why it's rejected" "$(cat /tmp/variant-reject.$$)"
_pass "overlay .macos.zprofile rejected with descriptive error"
rm -f /tmp/variant-reject.$$
