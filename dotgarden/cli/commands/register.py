"""`dotfile register` — move a config into the repo + symlink it back."""

import os
import shutil
import sys

from dotgarden import config, paths, symlinks
from dotgarden import registry as reg
from dotgarden.cli.utils.logging import LOG, color_header, color_hint, color_label
from dotgarden.cli.utils.overlays import resolve_overlay, validate_overlay_scope


def _register_is_interactive(args):
    """The register wizard fires on a tty unless --yes is set.

    Tests and CI pipelines run without a tty, so they fall through to the
    flag-based path — existing non-interactive tests keep passing without
    needing to mock anything. --yes + tty also bypasses the wizard, so
    scripts that pass all fields explicitly never see a prompt.
    """
    return sys.stdin.isatty() and not getattr(args, 'yes', False)


def _prompt_default(label, default, hint=None):
    """Prompt with a bracketed default. Empty reply → return default.

    The `label` renders in the wizard color scheme (cyan bold), the optional
    `hint` parenthetical (e.g. "macos / linux / none") renders dim, and the
    bracketed default also renders dim. When stdout isn't a tty or NO_COLOR
    is set, everything falls back to plain ASCII.

    If the user types "none" or "-" the result is `None` (explicitly
    clearing). Anything else becomes the new value.
    """
    display = default if default is not None else 'none'
    label_part = color_label(label)
    hint_part = f' {color_hint(f"({hint})")}' if hint else ''
    default_part = color_hint(f'[{display}]')
    response = input(f'  {label_part}{hint_part} {default_part}: ').strip()
    if not response:
        return default
    if response.lower() in ('none', '-'):
        return None
    return response


def _register_wizard(args, source_path, home_dir, overlay_dir, overlay_profile):
    """Prompt for any register field that wasn't specified via flag.

    Mutates args in place (argparse Namespace attributes). No-op when
    _register_is_interactive(args) is False.

    Scope:
      - category: default is auto-detected from path.
      - os: default is args.os, else none.
      - profile: default is args.profile; skipped entirely when an overlay
                 is active (the profile is implicit from overlay metadata).
    """
    if not _register_is_interactive(args):
        return

    # Section header + visual break before prompts, so the wizard is
    # distinguishable from any preceding LOG output.
    print()
    print(color_header('Register — configure missing fields'))
    print(color_hint('  (press Enter to accept the default, or type "none" to clear)'))

    if not args.category:
        auto = paths.auto_detect_category(source_path, home_dir)
        args.category = _prompt_default(
            'Category',
            auto,
            hint='path-based default; type a different name or "none"',
        )

    if args.os is None:
        chosen = _prompt_default('OS', None, hint='macos / linux / none')
        if chosen in ('macos', 'linux'):
            args.os = chosen
        elif chosen is not None:
            LOG.warning(f'Ignoring unsupported OS value: {chosen!r}')
            args.os = None

    # Skip profile prompt when overlay is active — the profile is fixed by
    # overlay metadata and was already set before this wizard ran.
    if args.profile is None and not overlay_dir:
        args.profile = _prompt_default('Profile', None, hint='e.g. work / home / none')


def _select_target_dir_and_registry(args, home_dir, main_dotfiles_dir, main_registry_path):
    """Decide where this `register` should write.

    Returns (dotfiles_dir, registry_path, overlay_dir, overlay_profile).
    overlay_dir / overlay_profile are None when targeting the main repo.

    Unlike `bootstrap`, register does NOT inherit an overlay from
    `.dotfiles_env` / `$DOTFILES_OVERLAY` just because a prior bootstrap
    happened to activate one. That was a surprise — users running
    `dotfile register ~/.zshrc` after a `dotfile bootstrap --overlay
    ~/dotfiles-work` found their registration silently landing in the
    overlay.

    The overlay is now targeted only when:
      1. `--overlay <dir>` was passed explicitly (unambiguous user intent), or
      2. `--profile <p>` was passed AND the env/file overlay declares that
         same profile (so the user's intent aligns with the overlay's scope).

    Anything else → main. This keeps "sticky" overlay state from bootstrap
    out of register's decision.
    """
    flag_overlay = getattr(args, 'overlay', None)

    if flag_overlay:
        # Explicit flag — honor it, regardless of env/file state.
        overlay_dir, _ = resolve_overlay(args, home_dir)
    elif args.profile:
        # No flag, but --profile was given. Accept the env/file overlay
        # only if its declared profile matches the requested one.
        env_overlay, _ = resolve_overlay(args, home_dir)
        overlay_dir = None
        if env_overlay:
            try:
                env_overlay_profile = symlinks._read_overlay_profile(env_overlay)
            except reg.RegistryError:
                env_overlay_profile = None
            if env_overlay_profile == args.profile:
                overlay_dir = env_overlay
            else:
                LOG.info(
                    f'Overlay at {env_overlay} declares profile '
                    f'{env_overlay_profile!r}; --profile is {args.profile!r}. '
                    f'Registering to main repo.'
                )
    else:
        # Neither --overlay nor --profile — register to main, even if a
        # sticky overlay is in .dotfiles_env.
        overlay_dir = None

    if not overlay_dir:
        return main_dotfiles_dir, main_registry_path, None, None

    overlay_profile = validate_overlay_scope(overlay_dir, main_dotfiles_dir, args.profile)
    # Mirror the overlay's profile onto args.profile so it's stored
    # consistently on the registry entry.
    args.profile = overlay_profile
    LOG.info(f'Registering to overlay {overlay_dir} (profile={overlay_profile})')
    registry_path = os.path.join(overlay_dir, config.REGISTRY_FILENAME)
    return overlay_dir, registry_path, overlay_dir, overlay_profile


def _check_cross_registry_conflicts(
    source_path, home_dir, main_dotfiles_dir, main_registry_path, overlay_dir
):
    """When targeting the overlay, also check the main registry for conflicts.

    Without this, a user can re-register a file that's already in main into
    the overlay (different registry file → no conflict in the overlay's own
    load), ending up with two entries for the same source_path.

    Returns the main-registry entry dict if one exists, else None. Caller
    decides how to surface it (error vs prompt).
    """
    if not overlay_dir:
        return None
    if not os.path.exists(main_registry_path):
        return None
    try:
        main_registry = reg.load(main_registry_path)
    except reg.RegistryError:
        return None
    return reg.find_by_source(main_registry, paths.format_for_display(source_path, home_dir))


def _confirm_replace_repo_file(repo_abs, source_path, home_dir, is_interactive):
    """When the repo already has a non-symlink file at the destination,
    prompt the user before overwriting it.

    Common case: the starter template ships a placeholder `.zshrc`, the user
    clones the repo and runs `dotfile register ~/.zshrc` to promote their
    real shell config. The naive behavior (error with "use --force") hides
    the intent — prompt instead so the user can say "yes, my home version
    is the one I want checked in".

    Returns True when the caller should proceed with the overwrite, False
    when the user declined (caller should bail).
    """
    repo_size = os.path.getsize(repo_abs)
    home_size = os.path.getsize(source_path)
    rel = os.path.relpath(repo_abs)
    src_display = paths.format_for_display(source_path, home_dir)
    print()
    print(color_header('Destination already exists in the repo'))
    print(f'  repo:  {rel}  ({repo_size} bytes)')
    print(f'  home:  {src_display}  ({home_size} bytes)')
    print(color_hint(
        '  The home file will replace the repo file. Useful when the repo '
        'ships a placeholder (e.g. a starter template) and you want your '
        'real version checked in. A diff preview is available.'
    ))
    if not is_interactive:
        # Non-interactive mode: keep the hard error — scripts shouldn't
        # silently overwrite tracked content.
        LOG.error(f'Destination already exists: {rel}')
        LOG.error('Run interactively to review + confirm, or pass --force to overwrite.')
        return False
    while True:
        response = input('  Replace repo file with home version? [y/N/diff]: ').strip().lower()
        if response in ('y', 'yes'):
            return True
        if response in ('', 'n', 'no'):
            print('  Skipped.')
            return False
        if response in ('d', 'diff'):
            _show_file_diff(repo_abs, source_path)
            continue
        print(f'  Unknown response {response!r}; expected y/N/diff.')


def _convention_repo_path(source_path, home_dir):
    """If `source_path` naturally maps to a convention-discovered location,
    return the repo-relative path that the convention would link from.

    Covers:
      - Root dotfiles:  ~/.zshrc         → ".zshrc"
      - .config/* tree: ~/.config/fish/  → ".config/fish"
                        ~/.config/fish/config.fish → ".config/fish/config.fish"

    Returns None for anything outside those two conventions
    (`~/Library/…`, `~/.claude/…`, `~/tools/…`, etc.) — those genuinely need
    a registry entry because the convention scanner won't find them.
    """
    rel = os.path.relpath(source_path, home_dir)
    if rel.startswith('..'):
        return None  # outside $HOME
    first = rel.split(os.sep, 1)[0]

    # .config/* convention: any file/dir under ~/.config/
    if first == config.DOT_CONFIG_DIR:
        return rel

    # Root dotfile convention: first segment is a dotfile at $HOME root.
    # Only single-segment paths qualify — `~/.claude/skills/…` is a
    # subdirectory of a dotfile, not a root dotfile itself, and belongs
    # in the registry.
    if os.sep not in rel and first.startswith('.'):
        return rel

    return None


def _show_file_diff(repo_abs, source_path):
    """Print a unified diff (repo → home) for user review inside the prompt."""
    import difflib

    try:
        with open(repo_abs, 'r') as f:
            repo_lines = f.readlines()
        with open(source_path, 'r') as f:
            home_lines = f.readlines()
    except UnicodeDecodeError:
        print('  (binary content — diff skipped)')
        return
    rel = os.path.relpath(repo_abs)
    diff = difflib.unified_diff(
        repo_lines, home_lines, fromfile=f'repo/{rel}', tofile=source_path, lineterm=''
    )
    printed = False
    for line in diff:
        print(f'    {line.rstrip()}')
        printed = True
    if not printed:
        print('  (files are identical)')


def cmd_register(args):
    """Register a file or directory into the dotfiles system."""
    cfg = config.defaults()
    main_dotfiles_dir = cfg['dotfiles_dir']
    home_dir = cfg['home_dir']
    main_registry_path = cfg['registry_path']

    dotfiles_dir, registry_path, overlay_dir, overlay_profile = _select_target_dir_and_registry(
        args, home_dir, main_dotfiles_dir, main_registry_path
    )

    try:
        source_path = paths.validate(args.path, dotfiles_dir, must_exist=True)
        LOG.info(f'Source path: {source_path}')

        registry = reg.load(registry_path)
        # Preserve overlay's `profile:` scope on every save — without this, a
        # register that writes to the overlay registry would strip the
        # top-level profile declaration from the YAML.
        if overlay_dir:
            registry['profile'] = overlay_profile

        existing = reg.find_by_source(registry, paths.format_for_display(source_path, home_dir))
        if existing and not args.force:
            LOG.error(f'File already registered as: {existing["id"]}')
            LOG.error('Use --force to re-register or unregister first')
            sys.exit(1)
        if existing and args.force:
            reg.remove(registry, existing['id'])
            LOG.info(f'Replacing existing registration: {existing["id"]}')

        # When the caller targets the overlay, registry-level uniqueness is
        # checked in the overlay's registry file only. Walk the main registry
        # too so we can catch a file that's already registered in main and
        # was about to get a shadow entry in the overlay.
        cross = _check_cross_registry_conflicts(
            source_path, home_dir, main_dotfiles_dir, main_registry_path, overlay_dir
        )
        if cross and not args.force:
            LOG.error(
                f'File {paths.format_for_display(source_path, home_dir)!r} is already '
                f'registered in the main repo as {cross["id"]!r}. '
                f'Unregister it there first (`dotfile unregister {cross["id"]}`) '
                f'or rerun with --force to shadow it in the overlay.'
            )
            sys.exit(1)
        if cross and args.force:
            LOG.warning(
                f'Source already registered in main as {cross["id"]!r}; overlay '
                f'entry will shadow it at bootstrap time.'
            )

        # Bail if the source is already a symlink into any known repo
        # (main OR overlay). Catches two scenarios:
        # 1. File was convention-registered previously (no registry entry,
        #    just a symlink into main). Re-registering would duplicate.
        # 2. File was registered in main, and now the user is trying to
        #    also register it in the overlay (source is a symlink into
        #    main, but we're targeting overlay).
        # --force bypasses, letting the later overwrite paths handle the
        # replacement.
        if os.path.islink(source_path) and not args.force:
            link_target = os.path.realpath(source_path)
            for candidate_dir, label in (
                (main_dotfiles_dir, 'main repo'),
                (overlay_dir, 'overlay') if overlay_dir else (None, None),
            ):
                if not candidate_dir:
                    continue
                candidate_abs = os.path.realpath(candidate_dir)
                if link_target == candidate_abs or link_target.startswith(
                    candidate_abs + os.sep
                ):
                    LOG.error(
                        f'{paths.format_for_display(source_path, home_dir)} is '
                        f'already a symlink into the {label} ({link_target}). '
                        f'Unregister it (or `rm` the symlink and move the file back) '
                        f'before re-registering, or pass --force to overwrite.'
                    )
                    sys.exit(1)

        # Prompt for any missing fields when running interactively. No-op on
        # non-tty (tests, CI) and when --yes is passed. When an overlay is
        # active, the overlay_profile is already inferred and baked into
        # args.profile — the wizard skips the profile prompt in that case.
        _register_wizard(
            args,
            source_path,
            home_dir,
            overlay_dir,
            overlay_profile if overlay_dir else None,
        )

        # Decide if this registration can skip the registry entirely — the
        # `.config/*` and root-dotfile conventions discover these paths at
        # bootstrap time without help from `__registry__.yaml`.
        #
        # Registry mode is forced when the user passes any of:
        #   --category, --name, --os, --profile, --overlay
        # Each of those is a signal that they want registry-controlled
        # placement (a specific category dir, a custom repo path, or OS/
        # profile-gated linking via `__os__/` / `__profile__/`).
        use_registry = True
        convention_path = None
        registry_flags = (
            args.category, args.name, args.os, args.profile, overlay_dir,
        )
        if not any(registry_flags):
            convention_path = _convention_repo_path(source_path, home_dir)
            if convention_path is not None:
                use_registry = False

        if not use_registry:
            repo_path = convention_path
            category = None
            entry_id = None
            LOG.info(
                f'Path matches a convention ({convention_path!r}); skipping '
                f'registry — bootstrap auto-discovers it.'
            )
        else:
            category = args.category
            if not category:
                category = paths.auto_detect_category(source_path, home_dir)
                if category:
                    LOG.info(f'Auto-detected category: {category}')
                else:
                    LOG.info('No category (home directory file, will be placed at repo root)')

            if category:
                repo_dir = f'_{category}'
            elif args.os:
                repo_dir = f'__{args.os}__'
            elif args.profile:
                repo_dir = f'__{args.profile}__'
            else:
                repo_dir = ''

            filename = args.name if args.name else os.path.basename(source_path)
            repo_path = os.path.join(repo_dir, filename)

            entry_id = reg.derive_id(repo_path)

        if use_registry:
            if reg.find_by_id(registry, entry_id) and not args.force:
                LOG.error(f'ID conflict: {entry_id} already exists')
                LOG.error('Use --name to specify a different name')
                sys.exit(1)
            if reg.find_by_id(registry, entry_id) and args.force:
                reg.remove(registry, entry_id)
        repo_abs = os.path.join(dotfiles_dir, repo_path)

        if os.path.exists(repo_abs) and not args.force:
            # Regular file at the destination → prompt to replace (the
            # "starter template ships a placeholder, user promotes their
            # real home version" flow). Directories and symlinks still
            # use the hard-error path because replacing them is a bigger
            # hammer than a prompt should reach for.
            if os.path.isfile(repo_abs) and not os.path.islink(repo_abs):
                if not _confirm_replace_repo_file(
                    repo_abs, source_path, home_dir, _register_is_interactive(args)
                ):
                    sys.exit(1)
            else:
                LOG.error(f'Destination already exists: {repo_path}')
                LOG.error('Use --force to overwrite')
                sys.exit(1)

        target_label = (
            f'overlay {overlay_dir} (profile: {overlay_profile})'
            if overlay_dir
            else ('main registry' if use_registry else 'main repo (convention, no registry)')
        )
        print('\n' + '=' * 60)
        print('REGISTRATION PREVIEW')
        print('=' * 60)
        print(f'Source:      {paths.format_for_display(source_path, home_dir)}')
        print(f'Destination: {repo_path}')
        print(f'Target:      {target_label}')
        if use_registry:
            print(f'Category:    {category or "(none - repo root)"}')
            print(f'OS:          {args.os or "all"}')
            print(f'Profile:     {args.profile or "all"}')
            print(f'ID:          {entry_id}')
        print('=' * 60)
        print('\nThis will:')
        print(f'  1. Move {paths.format_for_display(source_path, home_dir)}')
        print(f'     to {repo_path} (in {target_label})')
        print('  2. Create symlink at original location')
        if use_registry:
            print('  3. Add entry to __registry__.yaml')
        else:
            print('  3. (skipping registry — path matches the convention; '
                  'bootstrap auto-discovers it)')
        print()

        if args.dry_run:
            print('[DRY RUN] No changes made.')
            return

        if getattr(args, 'yes', False):
            print('[--yes] Proceeding without prompt.')
        else:
            response = input('Proceed? [y/N]: ').strip().lower()
            if response not in ['y', 'yes']:
                print('Cancelled.')
                return

        repo_parent = os.path.dirname(repo_abs)
        if not os.path.exists(repo_parent):
            os.makedirs(repo_parent)
            LOG.info(f'Created directory: {repo_parent}')

        LOG.info(f'Moving {source_path} to {repo_abs}')
        if os.path.exists(repo_abs):
            if os.path.isdir(repo_abs):
                shutil.rmtree(repo_abs)
            else:
                os.remove(repo_abs)
        if os.path.isdir(source_path):
            shutil.copytree(source_path, repo_abs, symlinks=True)
            shutil.rmtree(source_path)
        else:
            shutil.copy2(source_path, repo_abs)
            os.remove(source_path)

        LOG.info(f'Creating symlink: {source_path} -> {repo_abs}')
        os.symlink(repo_abs, source_path)

        if use_registry:
            entry = {
                'id': entry_id,
                'source_path': paths.format_for_display(source_path, home_dir),
                'repo_path': repo_path,
                'category': category,
                'os': args.os,
                'profile': args.profile,
            }
            reg.add(registry, entry)
            reg.save(registry, registry_path, dotfiles_dir)
            print(f'\n✓ Successfully registered: {entry_id}')
        else:
            # Overlay would have taken the registry path above — this branch
            # is main-repo convention only. No registry write; still save
            # the registry file if it didn't exist yet so subsequent
            # invocations find valid YAML (no-op when the file is already
            # present and unchanged).
            print(
                f'\n✓ Successfully linked: '
                f'{paths.format_for_display(source_path, home_dir)} → {repo_path}'
            )
            print('  (no registry entry — convention-discovered at bootstrap)')
            return
        print(f'  Symlink: {paths.format_for_display(source_path, home_dir)} -> {repo_path}')

    except (FileNotFoundError, ValueError) as e:
        LOG.error(str(e))
        sys.exit(1)
    except reg.RegistryError as e:
        LOG.error(str(e))
        sys.exit(1)
    except Exception as e:
        LOG.error(f'Unexpected error: {e}')
        import traceback

        traceback.print_exc()
        sys.exit(1)
