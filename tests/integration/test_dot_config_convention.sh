#!/usr/bin/env bash
# Verifies the .config/* convention: top-level children of <repo>/.config/
# auto-symlink to ~/.config/<name> without needing a registry entry.

set -euo pipefail
source "$(dirname "$0")/lib.sh"

trap teardown_workspace EXIT
setup_workspace

# Minimal repo — no registry entries for any of the .config/* tools.
cat > "$TEST_REPO/__registry__.yaml" <<EOF
version: '3.0'
os:
  - macos
  - linux
profiles:
  - work
  - home
EOF

# Two tools with typical file layouts plus one standalone config file.
mkdir -p "$TEST_REPO/.config/fish/conf.d"
mkdir -p "$TEST_REPO/.config/fish/functions"
mkdir -p "$TEST_REPO/.config/ghostty/themes"

cat > "$TEST_REPO/.config/fish/config.fish" <<'EOF'
# fish base config
set -gx EDITOR nvim
EOF
cat > "$TEST_REPO/.config/fish/conf.d/greeting.fish" <<'EOF'
function fish_greeting; end
EOF
cat > "$TEST_REPO/.config/fish/functions/hello.fish" <<'EOF'
function hello; echo hi; end
EOF

cat > "$TEST_REPO/.config/ghostty/config" <<'EOF'
background = 1d1f21
EOF
touch "$TEST_REPO/.config/ghostty/themes/catppuccin"

mkdir -p "$TEST_REPO/.config/standalone-tool"
# Also a single file directly at .config root (not inside a subdir).
echo "flat" > "$TEST_REPO/.config/notes"

assert_exit_zero "bootstrap with .config convention" \
    dotfile bootstrap --os linux

# Each top-level .config/* child symlinks as a whole.
assert_symlink_to "$TEST_HOME/.config/fish"              "$TEST_REPO/.config/fish"
assert_symlink_to "$TEST_HOME/.config/ghostty"           "$TEST_REPO/.config/ghostty"
assert_symlink_to "$TEST_HOME/.config/standalone-tool"   "$TEST_REPO/.config/standalone-tool"
assert_symlink_to "$TEST_HOME/.config/notes"             "$TEST_REPO/.config/notes"

# Contents are visible through the directory symlink.
assert_file_contains "$TEST_HOME/.config/fish/config.fish"                "EDITOR nvim"
assert_file_contains "$TEST_HOME/.config/fish/conf.d/greeting.fish"       "fish_greeting"
assert_file_contains "$TEST_HOME/.config/fish/functions/hello.fish"       "echo hi"
assert_file_contains "$TEST_HOME/.config/ghostty/config"                   "background"

# No .local files should have been generated for bases without variants.
assert_not_exists "$TEST_HOME/.config/fish/config.fish.local"
assert_not_exists "$TEST_HOME/.config/ghostty/config.local"
