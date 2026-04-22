#!/bin/zsh
# .zprofile — loaded once per login shell (before .zshrc).
# Good for: PATH setup, env vars, tool initialization.

export EDITOR=vim
export LANG=en_US.UTF-8

# Add local bin to PATH
export PATH="$HOME/.local/bin:$PATH"

# Personal scripts live in $DOTFILES/scripts; the `dotfile` command itself is
# installed via `uv tool install dotgarden` and doesn't need $DOTFILES on PATH.
export DOTFILES="$HOME/dotfiles"
export PATH="$DOTFILES/scripts:$PATH"

# Source OS and profile overrides via .local pattern.
# Bootstrap generates this file — see `dotfile bootstrap`.
[[ -f ~/.zprofile.local ]] && . ~/.zprofile.local
