# Fish shell configuration
# Equivalent to .zprofile + .zshrc for fish.

set -gx EDITOR vim
set -gx LANG en_US.UTF-8

# Dotfiles
set -gx DOTFILES "$HOME/dotfiles"
fish_add_path "$DOTFILES/scripts"
fish_add_path "$HOME/.local/bin"

# Parse ~/.dotfiles_env for OS and profile
if test -f ~/.dotfiles_env
    for line in (grep '^export ' ~/.dotfiles_env)
        set -l kv (string replace 'export ' '' $line)
        set -l key (string split -m1 '=' $kv)[1]
        set -l val (string split -m1 '=' $kv)[2]
        set -gx $key $val
    end
end

# Source OS-specific config
if test -n "$DOTFILES_OS"
    set -l os_config $DOTFILES/_fish/config.$DOTFILES_OS.fish
    if test -f $os_config
        source $os_config
    end
end

# Source profile-specific config
if test -n "$DOTFILES_PROFILE"
    set -l profile_config $DOTFILES/_fish/config.$DOTFILES_PROFILE.fish
    if test -f $profile_config
        source $profile_config
    end
end

# Git aliases
alias gs 'git status'
alias gd 'git diff'
alias gc 'git commit'
alias gl 'git log --oneline --graph --decorate -20'
