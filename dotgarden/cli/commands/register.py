"""`dotfile register` — move a config into the repo + symlink it back."""

import os
import shutil
import sys

from dotgarden import config, paths
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
    """Decide where this `register` should write and mutate args.profile if
    inferred from an overlay.

    Returns (dotfiles_dir, registry_path, overlay_dir, overlay_profile).
    overlay_dir / overlay_profile are None when no overlay is active.

    The function is the single place that:
      - resolves the overlay (flag > env > .dotfiles_env),
      - validates it (same-dir check, reads profile, matches vs --profile),
      - and picks the final write target (overlay vs main).

    cmd_register's body then just does "normal register, but targeting
    `dotfiles_dir` / `registry_path`" — no more inline if-overlay branches.
    """
    overlay_dir, _source = resolve_overlay(args, home_dir)
    if not overlay_dir:
        return main_dotfiles_dir, main_registry_path, None, None

    overlay_profile = validate_overlay_scope(overlay_dir, main_dotfiles_dir, args.profile)
    # Infer profile from overlay when not explicitly passed. Stored on
    # the entry for consistency, even though it's implicit in the overlay.
    args.profile = overlay_profile
    LOG.info(f'Registering to overlay {overlay_dir} (profile={overlay_profile})')

    dotfiles_dir = overlay_dir
    registry_path = os.path.join(overlay_dir, config.REGISTRY_FILENAME)
    return dotfiles_dir, registry_path, overlay_dir, overlay_profile


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

        if reg.find_by_id(registry, entry_id) and not args.force:
            LOG.error(f'ID conflict: {entry_id} already exists')
            LOG.error('Use --name to specify a different name')
            sys.exit(1)
        if reg.find_by_id(registry, entry_id) and args.force:
            reg.remove(registry, entry_id)
        repo_abs = os.path.join(dotfiles_dir, repo_path)

        if os.path.exists(repo_abs) and not args.force:
            LOG.error(f'Destination already exists: {repo_path}')
            LOG.error('Use --force to overwrite')
            sys.exit(1)

        target_label = (
            f'overlay {overlay_dir} (profile: {overlay_profile})'
            if overlay_dir
            else 'main registry'
        )
        print('\n' + '=' * 60)
        print('REGISTRATION PREVIEW')
        print('=' * 60)
        print(f'Source:      {paths.format_for_display(source_path, home_dir)}')
        print(f'Destination: {repo_path}')
        print(f'Target:      {target_label}')
        print(f'Category:    {category or "(none - repo root)"}')
        print(f'OS:          {args.os or "all"}')
        print(f'Profile:     {args.profile or "all"}')
        print(f'ID:          {entry_id}')
        print('=' * 60)
        print('\nThis will:')
        print(f'  1. Move {paths.format_for_display(source_path, home_dir)}')
        print(f'     to {repo_path} (in {target_label})')
        print('  2. Create symlink at original location')
        print('  3. Add entry to __registry__.yaml')
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
