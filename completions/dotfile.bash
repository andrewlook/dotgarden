# Bash completion for dotfile command

_dotfile() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD - 1]}"

    commands="register list status unregister ids env doctor bootstrap"
    # Descriptions (for reference): register, list (all managed files),
    # status (symlink health), unregister, ids, doctor, bootstrap

    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=($(compgen -W "${commands}" -- "${cur}"))
        return 0
    fi

    case "${COMP_WORDS[1]}" in
        register)
            if [[ "${cur}" == -* ]]; then
                COMPREPLY=($(compgen -W "--category --os --profile --name --dry-run --force" -- "${cur}"))
            else
                COMPREPLY=($(compgen -f -- "${cur}"))
            fi
            ;;
        list)
            COMPREPLY=($(compgen -W "--json" -- "${cur}"))
            ;;
        unregister)
            if [[ "${cur}" == -* ]]; then
                COMPREPLY=($(compgen -W "--dry-run --no-restore --keep-symlink --keep-file" -- "${cur}"))
            else
                local ids
                ids=$(dotfile ids 2>/dev/null)
                COMPREPLY=($(compgen -W "${ids}" -- "${cur}"))
            fi
            ;;
        doctor)
            COMPREPLY=($(compgen -W "--dry-run" -- "${cur}"))
            ;;
        bootstrap)
            case "${prev}" in
                --os)
                    COMPREPLY=($(compgen -W "macos linux" -- "${cur}"))
                    ;;
                --profile)
                    COMPREPLY=($(compgen -W "work home" -- "${cur}"))
                    ;;
                --overlay)
                    COMPREPLY=($(compgen -d -- "${cur}"))
                    ;;
                *)
                    COMPREPLY=($(compgen -W "--os --profile --skip-registry --overlay --dry-run" -- "${cur}"))
                    ;;
            esac
            ;;
    esac
}

complete -F _dotfile dotfile
