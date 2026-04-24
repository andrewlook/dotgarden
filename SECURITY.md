# Security Policy

## Supported versions

dotgarden follows zero-based SemVer while pre-1.0. Only the latest
`0.x` minor line receives security fixes; older minors are unsupported
once a new minor is released.

| Version | Supported          |
|---------|--------------------|
| `0.3.x` | :white_check_mark: |
| `< 0.3` | :x:                |

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** through GitHub's
[private vulnerability reporting](https://github.com/andrewlook/dotgarden/security/advisories/new)
flow. Do not open a public issue.

You should expect:
- Acknowledgement within 7 days.
- A status update within 14 days, including whether the report is
  accepted, requires more info, or has been declined with rationale.
- A coordinated disclosure timeline once a fix is in flight.

If you do not receive a response within 14 days, feel free to ping the
maintainer in a public issue **without** disclosing details — just say
"awaiting response on a private security report."

## Scope

In scope:
- Arbitrary code execution via crafted `__registry__.yaml` or overlay
  manifests.
- Symlink traversal or path-injection that lets `dotfile bootstrap`
  write outside the intended `$HOME` target.
- Credential or secret exposure via the published wheel/sdist or via
  the dependency tree.
- Supply chain attacks against the release pipeline (publish workflow,
  trusted publishing, action SHAs).

Out of scope:
- Performance regressions or DoS via `dotfile bootstrap` on very large
  repositories — `dotgarden` is single-user CLI tooling, not a server.
- User-side configuration mistakes (e.g., committing private keys to a
  dotfiles repo). dotgarden does not exfiltrate files; what you put in
  the repo, you ship.
- Issues only reproducible on unsupported Python versions (`< 3.10`).

## Verifying release artifacts

Every release published to PyPI from `v0.3.0` onward ships PEP 740
artifact attestations. See the README's "Verifying release
attestations" section for the verification command.
