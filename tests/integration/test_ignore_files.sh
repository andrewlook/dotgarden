#!/usr/bin/env bash
# A file listed under ignore_files in __registry__.yaml must NOT be linked by
# bootstrap and must NOT show up in `dotfile status` output.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

copy_fixture_to_repo "$(dirname "$0")/../../examples/minimal"

# Add a file that looks like a dotfile but should be excluded via registry.
echo 'print("hello")' > "$TEST_REPO/build.py"

cat > "$TEST_REPO/__registry__.yaml" <<'EOF'
version: '3.0'
ignore_files:
- build.py
EOF

assert_exit_zero "bootstrap" dotfile bootstrap --os linux

# build.py must NOT be symlinked into HOME.
assert_not_exists "$TEST_HOME/build.py"

# Baseline sanity: a normal dotfile from the fixture was linked.
assert_symlink "$TEST_HOME/.gitconfig"

# build.py must not surface in `dotfile status`.
run_capture /tmp/status-ignore.$$ dotfile status
assert_file_not_contains /tmp/status-ignore.$$ "build.py"
rm -f /tmp/status-ignore.$$
