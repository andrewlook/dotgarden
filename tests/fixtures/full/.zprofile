# Full example — common zprofile with .local override
export EDITOR=vim
export PATH="$HOME/bin:$PATH"
[[ -f ~/.zprofile.local ]] && . ~/.zprofile.local
