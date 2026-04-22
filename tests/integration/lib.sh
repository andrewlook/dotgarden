# Assertion helpers for integration tests.
# Each test sources this, uses the helpers, and `exit 1` on failure.

# Colors (only when stdout is a tty)
if [ -t 1 ]; then
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
    C_RED=''; C_GREEN=''; C_YELLOW=''; C_DIM=''; C_RESET=''
fi

_fail() {
    printf '%s✗%s %s\n' "$C_RED" "$C_RESET" "$1" >&2
    [ -n "${2:-}" ] && printf '  %s%s%s\n' "$C_DIM" "$2" "$C_RESET" >&2
    exit 1
}

_pass() {
    printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$1"
}

# Create an isolated HOME + repo workspace. Exports TEST_HOME, TEST_REPO, DOTFILES, HOME.
# Prior HOME is saved into ORIG_HOME for cleanup.
setup_workspace() {
    export TEST_TMPDIR=$(mktemp -d -t dotgarden-integ-XXXXXX)
    export TEST_HOME="$TEST_TMPDIR/home"
    export TEST_REPO="$TEST_TMPDIR/repo"
    mkdir -p "$TEST_HOME" "$TEST_REPO"
    export ORIG_HOME="${HOME:-}"
    export HOME="$TEST_HOME"
    export DOTFILES="$TEST_REPO"
}

teardown_workspace() {
    if [ -n "${TEST_TMPDIR:-}" ] && [ -d "$TEST_TMPDIR" ]; then
        rm -rf "$TEST_TMPDIR"
    fi
    [ -n "${ORIG_HOME:-}" ] && export HOME="$ORIG_HOME"
}

# Copy a fixture directory (e.g. examples/full/) into $TEST_REPO, flat.
copy_fixture_to_repo() {
    local src="$1"
    [ -d "$src" ] || _fail "fixture not found: $src"
    cp -R "$src"/. "$TEST_REPO/"
    # Ensure dotfiles inside the fixture have predictable mtimes
    find "$TEST_REPO" -type f -exec touch {} +
}

# --- Assertions ---

assert_symlink() {
    local path="$1"
    [ -L "$path" ] || _fail "expected symlink at $path" "$(ls -la "$(dirname "$path")" 2>&1 | head)"
    _pass "symlink exists: ${path#$TEST_HOME/}"
}

assert_symlink_to() {
    local link="$1" expected="$2"
    [ -L "$link" ] || _fail "expected symlink at $link"
    local actual
    actual=$(readlink "$link")
    # Compare resolved absolute paths so ~/foo vs /abs/foo don't false-negative.
    local actual_abs expected_abs
    actual_abs=$(cd "$(dirname "$link")" && realpath "$actual" 2>/dev/null || echo "$actual")
    expected_abs=$(realpath "$expected" 2>/dev/null || echo "$expected")
    [ "$actual_abs" = "$expected_abs" ] \
        || _fail "symlink $link points to $actual_abs" "expected: $expected_abs"
    _pass "symlink $link -> ${expected#$TEST_TMPDIR/}"
}

assert_regular_file() {
    local path="$1"
    [ -f "$path" ] && [ ! -L "$path" ] \
        || _fail "expected regular file (not symlink) at $path"
    _pass "regular file at ${path#$TEST_HOME/}"
}

assert_not_exists() {
    local path="$1"
    if [ -e "$path" ] || [ -L "$path" ]; then
        _fail "expected $path to not exist" "$(ls -la "$path" 2>&1)"
    fi
    _pass "absent: ${path#$TEST_HOME/}"
}

assert_file_contains() {
    local path="$1" needle="$2"
    [ -f "$path" ] || _fail "file $path does not exist"
    grep -q -F -- "$needle" "$path" \
        || _fail "expected $path to contain \"$needle\"" "$(cat "$path")"
    _pass "file ${path#$TEST_HOME/} contains \"$needle\""
}

assert_file_not_contains() {
    local path="$1" needle="$2"
    [ -f "$path" ] || _fail "file $path does not exist"
    if grep -q -F -- "$needle" "$path"; then
        _fail "expected $path NOT to contain \"$needle\"" "$(cat "$path")"
    fi
    _pass "file ${path#$TEST_HOME/} does not contain \"$needle\""
}

assert_exit_zero() {
    local label="$1"; shift
    local rc=0
    "$@" >/tmp/assert-out.$$ 2>&1 || rc=$?
    if [ "$rc" -ne 0 ]; then
        _fail "$label exited non-zero ($rc)" "$(cat /tmp/assert-out.$$)"
    fi
    rm -f /tmp/assert-out.$$
    _pass "$label succeeded"
}

assert_exit_nonzero() {
    local label="$1"; shift
    local rc=0
    "$@" >/tmp/assert-out.$$ 2>&1 || rc=$?
    if [ "$rc" -eq 0 ]; then
        _fail "$label unexpectedly succeeded" "$(cat /tmp/assert-out.$$)"
    fi
    rm -f /tmp/assert-out.$$
    _pass "$label failed as expected (rc=$rc)"
}

# Capture command output to a file so subsequent assertions can grep it.
run_capture() {
    local outfile="$1"; shift
    "$@" > "$outfile" 2>&1 || {
        local rc=$?
        cat "$outfile" >&2
        _fail "command failed: $*" "rc=$rc"
    }
}
