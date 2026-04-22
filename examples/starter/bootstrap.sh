#!/usr/bin/env bash
set -euo pipefail

# Quick bootstrap for a new machine.
# Usage: curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/dotfiles/main/bootstrap.sh | bash -s -- --os macos

DOTFILES_DIR="$HOME/dotfiles"
REPO_URL="${DOTFILES_REPO:-https://github.com/YOUR_USERNAME/dotfiles.git}"

echo "==> Installing dotfiles"

# Install uv if not present
if ! command -v uv &>/dev/null; then
    echo "==> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install dotgarden
if ! command -v dotfile &>/dev/null; then
    echo "==> Installing dotgarden..."
    uv tool install dotgarden
fi

# Clone dotfiles if not present
if [[ ! -d "$DOTFILES_DIR" ]]; then
    echo "==> Cloning dotfiles..."
    git clone "$REPO_URL" "$DOTFILES_DIR"
fi

cd "$DOTFILES_DIR"

# Run bootstrap with provided arguments
echo "==> Running dotfile bootstrap..."
dotfile bootstrap "$@"

echo ""
echo "==> Done! Source your shell config to activate:"
echo "    source ~/.zprofile"
