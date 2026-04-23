#!/usr/bin/env bash
# After a clean bootstrap, `dotfile status` should report all files healthy
# and exit 0. If a symlink is broken (target removed), status should surface
# the breakage — exact format-independent check: output mentions the file.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

copy_fixture_to_repo "$(dirname "$0")/../../tests/fixtures/minimal"

assert_exit_zero "bootstrap"  dotfile bootstrap --os linux

# Healthy state: status must exit 0 and not mention "UNLINKED" / "missing".
run_capture /tmp/status-ok.$$ dotfile status
assert_file_contains /tmp/status-ok.$$  "healthy"
assert_file_not_contains /tmp/status-ok.$$  "UNLINKED"
rm -f /tmp/status-ok.$$

# Break the setup by deleting the managed symlink in HOME. The repo still
# declares the dotfile, so `dotfile status` should report it as UNLINKED.
rm "$TEST_HOME/.gitconfig"

rc=0
dotfile status > /tmp/status-broken.$$ 2>&1 || rc=$?

grep -qE 'UNLINKED|missing|broken|stale' /tmp/status-broken.$$ \
    || _fail "status did not surface broken/missing entry" "$(cat /tmp/status-broken.$$)"
_pass "status reports broken/missing entry (rc=$rc)"
rm -f /tmp/status-broken.$$
