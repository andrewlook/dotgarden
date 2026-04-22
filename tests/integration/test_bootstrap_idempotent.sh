#!/usr/bin/env bash
# Running bootstrap twice must be safe: the second run reports all entries
# as already-ok, creates no new .bak files, and the status command exits 0.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

copy_fixture_to_repo "$(dirname "$0")/../../examples/full"

assert_exit_zero "first bootstrap"  dotfile bootstrap --os linux --profile work
first_snapshot=$(ls -la "$TEST_HOME" | sort)

assert_exit_zero "second bootstrap" dotfile bootstrap --os linux --profile work
second_snapshot=$(ls -la "$TEST_HOME" | sort)

if [ "$first_snapshot" != "$second_snapshot" ]; then
    echo "HOME contents diverged between bootstrap runs:" >&2
    diff <(echo "$first_snapshot") <(echo "$second_snapshot") >&2 || true
    _fail "bootstrap is not idempotent"
fi
_pass "idempotent: HOME contents unchanged across two bootstraps"

# No .bak files should exist (no user content was in the way).
if compgen -G "$TEST_HOME/*.bak" >/dev/null; then
    _fail "unexpected .bak files after idempotent run" "$(ls "$TEST_HOME"/*.bak)"
fi
_pass "no spurious .bak files created"

assert_exit_zero "dotfile status (healthy)" dotfile status
