#!/usr/bin/env bash
# Runs every test_*.sh in this directory, each in a subshell for isolation.
# Prints a summary and exits non-zero if any test fails.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

pass=0
fail=0
failed_tests=()

# Colors
if [ -t 1 ]; then
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
    C_RED=''; C_GREEN=''; C_BOLD=''; C_DIM=''; C_RESET=''
fi

# Verify the dotfile CLI is available. Tests must run against the installed
# entry-point, not the source bin/ shebang.
if ! command -v dotfile >/dev/null 2>&1; then
    echo "ERROR: 'dotfile' not on PATH. Install with: uv tool install ." >&2
    exit 2
fi

for t in test_*.sh; do
    [ -f "$t" ] || continue
    printf '\n%s==> %s%s\n' "$C_BOLD" "$t" "$C_RESET"
    if bash "$t"; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        failed_tests+=("$t")
    fi
done

printf '\n%s──────────────────────────────────────────%s\n' "$C_DIM" "$C_RESET"
printf '%d passed, %d failed\n' "$pass" "$fail"

if [ "$fail" -gt 0 ]; then
    printf '\n%sFailed tests:%s\n' "$C_RED" "$C_RESET"
    for t in "${failed_tests[@]}"; do
        printf '  - %s\n' "$t"
    done
    exit 1
fi
