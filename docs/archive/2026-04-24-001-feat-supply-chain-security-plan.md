---
title: "feat: incremental supply chain security for dotgarden"
type: feat
status: completed
date: 2026-04-24
completed: 2026-04-26
shipped_in: andrewlook/dotgarden#11
---

# feat: incremental supply chain security for dotgarden

**Target repo:** `andrewlook/dotgarden` (public). Plan lives here but could
plausibly migrate to the dotfiles repo; paths throughout are relative to
the dotgarden repo root.

## Overview

dotgarden is public and wired up to publish to PyPI via trusted
publishing, but the repo hasn't adopted the usual supply-chain hygiene
yet: no CVE scanning in CI, no Dependabot, no Ruff security rules, no
SECURITY.md, and GitHub Actions pinned to floating tags rather than
immutable commit SHAs. This plan layers in the practices from Bernat
Gabor's ["Securing the Python Supply Chain"](https://bernat.tech/posts/securing-python-supply-chain/)
that make sense for a small single-maintainer CLI, skipping the
practices that only pay off at enterprise scale.

The result: CVE-scanned deps, automated bump PRs, SHA-pinned actions,
security-lint enforcement, a published disclosure policy, and verified
provenance attestations on the PyPI release — all before the first
`v0.3.0` tag lands.

## Problem Frame

Three pressures converge:

1. **Public repo + PyPI imminent.** `andrewlook/dotgarden` went public
   recently; a tag push triggers `publish.yml` and ships a real wheel.
   Any dependency compromise or workflow-level exploit immediately
   affects downstream `uv tool install dotgarden` users.
2. **Lean team, low friction budget.** One maintainer. Practices that
   require ongoing babysitting (manual vuln triage, weekly artifact
   review) won't survive; automation has to carry the weight.
3. **What's already in place is good, but sparse.** Trusted publishing,
   deployment environment gate, and a lockfile exist. The gaps are the
   surrounding hygiene — detection (CVE scan, lint), maintenance
   (dependabot), and hardening (SHA pins, disclosure policy).

Bernat's post organizes practices into three phases. This plan adopts
most of Phase 1 and 2 (high leverage, low cost), a targeted subset of
Phase 3 (SHA-pinning + zizmor audit), and defers the rest as
separately-trackable follow-ups.

## Requirements Trace

- **R1.** Runtime dependencies scanned for known CVEs on every PR and
  weekly on the default branch.
- **R2.** Dependency and GitHub Actions updates surface automatically
  as PRs, with enough signal (changelog, CVE fixes) for fast review.
- **R3.** Ruff catches common Python security footguns (`bandit` rules)
  on every commit via the existing pre-commit hook.
- **R4.** Every third-party GitHub Action is pinned to an immutable
  commit SHA. Floating tags (`@v6`, `@release/v1`) are replaced with
  `actionsname@<40-char-sha>  # v6.0.2` comment-annotated pins.
- **R5.** The repo has a `SECURITY.md` describing how to report
  vulnerabilities privately, and a `CODEOWNERS` file routing security-
  touching files to the maintainer.
- **R6.** Every PyPI publish generates and uploads PEP 740 artifact
  attestations (already automatic at `pypa/gh-action-pypi-publish`
  v1.11+), and the release notes link to how consumers can verify them.
- **R7.** `zizmor` or an equivalent GitHub Actions static analyzer
  runs on every PR touching `.github/workflows/`.

## Scope Boundaries

- **Not in scope:** Hash-pinning runtime dependencies
  (`uv pip compile --generate-hashes`). dotgarden has one dep (`pyyaml`),
  and `uv.lock` already gives us deterministic resolution. Hash-pins add
  regeneration friction for marginal benefit at this scale.
- **Not in scope:** SBOM generation (`cyclonedx-py`). Worth having
  eventually; not worth a CI step for a 1-dep CLI today.
- **Not in scope:** `--exclude-newer` delayed ingestion. Overkill for a
  project with ~1 dep and a single maintainer who reviews bump PRs.
- **Not in scope:** Internal package mirror / devpi. Enterprise tool for
  an enterprise problem.

### Deferred to Separate Tasks

- **Typosquat PyPI placeholders** (`dot-garden`, `dot_garden`,
  `dotgardens`): already in the user's backlog per prior planning;
  administrative PyPI registration, not a code change. Track as a
  separate issue after first real release.
- **GitHub Advanced Security / CodeQL**: nice to have for a Python
  project. Private runs are free for public repos; consider as a follow-
  up PR once the rest of this plan lands.
- **Sigstore keyless signing of release artifacts**: the PyPA publish
  action handles attestations; additional signing is a further step.

## Context & Research

### Relevant Code and Patterns

- `.github/workflows/publish.yml` — already has `permissions: id-token:
  write`, `environment: pypi`, and uses `pypa/gh-action-pypi-publish@release/v1`.
  The attestation path is implicit; this plan makes it explicit.
- `.github/workflows/tests.yml` — unit + Docker integration jobs using
  `actions/checkout@v6`, `astral-sh/setup-uv@v8.1.0`. Actions are
  tag-pinned; R4 will SHA-pin them.
- `ruff.toml` — currently selects `E, F, W, I, TID`. R3 adds the `S`
  (flake8-bandit) rule set; the `TID251` pattern already shows how
  per-file ignores work for test files.
- `hooks/pre-commit` — wraps `pre-commit` with an auto-stage
  convenience layer. New ruff rules flow through it for free.
- `pyproject.toml` — sole runtime dep is `pyyaml >= 6.0`. Small surface
  to protect but still a real one (pyyaml has had CVEs historically).
- No `SECURITY.md`, `CODEOWNERS`, or `dependabot.yml` in the repo today.

### Institutional Learnings

- **No prior entries in `docs/solutions/`** touch supply-chain
  specifically. The most adjacent learning is the `.gitmodules` +
  submodule churn (we removed submodules from dotfiles because they
  added friction), which reinforces the "automation carries the weight"
  principle: manual bump steps tend to rot.
- From the recent workflow-version bump: floating major tags aren't
  always published (`astral-sh/setup-uv` has no `v8` alias, only
  `v8.1.0`). SHA-pinning will actually simplify this — dependabot
  proposes a new SHA plus a human-readable comment, no more manual tag
  hunting.

### External References

- Bernat Gabor, ["Securing the Python Supply Chain"](https://bernat.tech/posts/securing-python-supply-chain/)
  — primary source for practice taxonomy.
- `pip-audit` official action: [pypa/gh-action-pip-audit](https://github.com/pypa/gh-action-pip-audit)
  — installs and runs `pip-audit` in CI.
- `zizmor`: [github.com/woodruffw/zizmor](https://github.com/woodruffw/zizmor)
  — static analyzer for GitHub Actions workflows. `uvx zizmor .` works
  locally; there's also a `zizmors/zizmor-action` for CI.
- Dependabot config reference: [docs.github.com/code-security/dependabot](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference).
- PEP 740 attestations: [docs.pypi.org/attestations](https://docs.pypi.org/attestations/).
- SHA-pinning rationale: [docs.github.com/actions/security](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-third-party-actions#using-third-party-actions).

## Key Technical Decisions

- **D1. Adopt Phase 1 + most of Phase 2 + targeted Phase 3 from the
  reference post.** Skip hash-pins, SBOMs, delayed ingestion, and
  internal mirrors as overkill for a 1-dep single-maintainer CLI.
- **D2. Dependabot lands BEFORE SHA-pinning.** Without dependabot, SHA
  pins rot on ignored (updates become invisible); with it, bumps flow
  as reviewable PRs automatically. Sequencing matters — SHA-pinning
  dependabot itself is the final step so the helper that keeps the
  pins fresh is also pinned.
- **D3. `pip-audit` as a dedicated CI job, not a pre-commit hook.**
  Network dependency + potentially flaky against transient registry
  issues; CI job with its own retry semantics is more robust than a
  local hook.
- **D4. SHA-pins include the human-readable version as a comment.**
  `actions/checkout@<sha>  # v6.0.2` — dependabot preserves this
  convention when proposing bumps, so reviewers see both the SHA and
  the version at a glance.
- **D5. `SECURITY.md` uses private vulnerability reporting via GitHub
  (not an email address).** GH-native private reporting gives a
  trackable, auditable channel without needing to maintain a separate
  mailbox.
- **D6. Ruff `S` rules adopted gradually.** Enable the set, then
  `# noqa: S…` any existing violation that's a knowing choice, fix any
  that's a real bug. Expect most violations in test fixtures (hardcoded
  tempdir paths, `assert` usage) — use `per-file-ignores` for
  `tests/**` where appropriate.

## Open Questions

### Resolved During Planning

- **Hash-pin runtime deps too?** → No (D1). 1 dep, lockfile already
  gives determinism, hash regeneration friction outweighs benefit.
- **Dependabot vs. Renovate?** → Dependabot. GitHub-native, zero extra
  config, covers both pip deps and GitHub Actions. Renovate is stronger
  for polyrepo monorepos; not our shape.
- **`pip-audit` via `pypa/gh-action-pip-audit` or direct `uvx
  pip-audit`?** → Direct `uvx pip-audit --strict` via a single run
  step. Less machinery, works the same in CI and locally.

### Deferred to Implementation

- **Exact list of existing `ruff S` violations.** Can't know until the
  rule is enabled. Triage happens during Unit 3 — either `# noqa` with
  a rationale or rewrite.
- **Whether `zizmor` flags the current workflows.** Expect it to flag
  `permissions: id-token: write` at the top-level job level as fine
  (that's the attested-publish pattern); any other findings handled
  during Unit 6.
- **Whether `CODEOWNERS` should include `tests/` and `examples/`.**
  Decide during Unit 5 based on what feels least ceremonial; the repo
  is single-maintainer so any CODEOWNERS is effectively
  "`* @andrewlook`".

## Implementation Units

- [ ] **Unit 1: Dependabot config for Python deps + GitHub Actions**

**Goal:** Automated PRs bumping runtime deps, dev deps, and workflow
action versions. Lands first so SHA-pinning in Unit 4 has an auto-
maintainer already in place.

**Requirements:** R2.

**Dependencies:** None.

**Files:**
- Create: `.github/dependabot.yml`

**Approach:**
- Two `updates` entries: `package-ecosystem: "pip"` for the Python
  package itself, and `package-ecosystem: "github-actions"` for
  `.github/workflows/**`.
- `schedule.interval: "weekly"` for both — daily is noisy for a single-
  maintainer repo.
- `allow` nothing explicitly; default ruleset covers direct + indirect
  deps.
- Add `commit-message.prefix: "deps"` and `prefix-development: "deps-dev"`
  so bump PRs sort consistently in history.
- `open-pull-requests-limit: 5` for each ecosystem; at 1 dep + ~3
  actions today this is effectively uncapped.

**Patterns to follow:**
- GitHub's own [`dependabot-config` examples](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference) — stay close to the canonical layout for reviewer familiarity.

**Test scenarios:**
- Integration: push the config, verify the Dependabot tab in GitHub's
  Insights renders both ecosystems with the configured schedule. No
  unit tests — GitHub runs dependabot, not our code.
- Test expectation: none — configuration file with no behavioral change
  to the package itself.

**Verification:**
- `.github/dependabot.yml` validates in the GitHub UI (Insights →
  Dependency graph → Dependabot).
- Within ~24 hours of landing, at least one bump PR appears (or GH
  reports "no updates available" cleanly).

---

- [ ] **Unit 2: CVE scanning with `pip-audit` in CI**

**Goal:** Every PR and every push to `main` runs `pip-audit` against
the installed dep tree. Build fails on any known CVE unless explicitly
allowed.

**Requirements:** R1.

**Dependencies:** None. Parallel with Unit 1.

**Files:**
- Modify: `.github/workflows/tests.yml` (add `audit` job)

**Approach:**
- New job `audit` in `tests.yml`, `runs-on: ubuntu-latest`, matrix over
  nothing (single run).
- Steps:
  1. `actions/checkout@<sha>` (SHA will be added in Unit 4; for now
     reuse the tag-pinned form from existing jobs).
  2. `astral-sh/setup-uv@<sha>` (same note).
  3. `uvx pip-audit --strict --disable-pip` — the `--disable-pip` flag
     keeps pip-audit from invoking pip subprocesses.
  4. Optional: weekly `schedule:` trigger (`cron: '0 12 * * 1'`) so
     CVEs are caught even without PR activity.
- Add the weekly schedule via `on.schedule` at the workflow level; the
  existing jobs don't need to run on cron, so scope it carefully or
  split into a separate `security.yml` workflow. Decide during
  implementation — split wins if the `audit` job is meaningfully
  different (different trigger set, different lifecycle).

**Patterns to follow:**
- Existing job structure in `.github/workflows/tests.yml`.

**Test scenarios:**
- Happy path: clean dep tree → job exits 0, green check on the PR.
- Error path: intentionally add a known-CVE dep (e.g., old `pyyaml<5.4`)
  in a throwaway branch → job exits non-zero with the CVE in the log.
  Revert before merging.
- Integration: the job runs on `pull_request` and `push` to main; PR
  status check blocks merge until it passes.

**Verification:**
- CI shows an `audit` status check on every PR.
- Weekly run appears in the Actions tab with green (or red → a real
  CVE to triage).

---

- [ ] **Unit 3: Ruff `S` (flake8-bandit) security rules**

**Goal:** Common Python security mistakes (`subprocess` without
`shell=False`, weak hashes, hardcoded tempfile paths, etc.) fail lint
alongside the existing ruff rules.

**Requirements:** R3.

**Dependencies:** None. Can land alongside Units 1/2.

**Execution note:** Enable the rule set, then triage existing findings
— each either gets a targeted `# noqa: S…` with a one-line rationale
or a real fix. Don't mass-ignore with `per-file-ignores` until after
the first triage pass.

**Files:**
- Modify: `ruff.toml` (add `S` to `select`, add `per-file-ignores` for
  tests if warranted)
- Modify: source files in `dotgarden/` as needed to address flagged
  findings
- Possibly modify: `tests/**/*.py` if violations there are intentional
  (e.g., `assert` statements inside pytest are fine; Ruff's `S101`
  will flag them unless per-file-ignored)

**Approach:**
- Update `ruff.toml` `select = ["E", "F", "W", "I", "TID", "S"]`.
- Run `ruff check . --output-format=concise` and bucket the findings:
  - `S101` (assert used) in `tests/**` → `per-file-ignores` entry,
    since pytest tests use `assert` everywhere.
  - `S603` (subprocess call) in `dotgarden/symlinks.py` or similar →
    verify the input is not user-controlled, add `# noqa: S603` with
    a rationale if safe.
  - Anything else → fix on the spot.
- Update `AGENTS.md` if we add any project-wide "ignore because X"
  patterns that future contributors should know about.

**Patterns to follow:**
- Existing `per-file-ignores` in `ruff.toml` for `dotgarden/**.py` →
  `["TID251"]`. Same shape applies to `tests/**` → `["S101"]` if
  needed.

**Test scenarios:**
- Happy path: `mise run lint` passes on the branch.
- Happy path: each `# noqa: S…` in the diff has a comment explaining
  why (reviewer signal, not automatically tested).
- Integration: pre-commit hook runs the new rules on staged files
  (this is automatic once `ruff.toml` is updated).

**Verification:**
- `uv run --with ruff ruff check .` exits 0 on the branch with the new
  rule set enabled.
- Existing tests still pass.

---

- [ ] **Unit 4: SHA-pin third-party GitHub Actions**

**Goal:** Replace floating tags (`actions/checkout@v6`,
`astral-sh/setup-uv@v8.1.0`, `pypa/gh-action-pypi-publish@release/v1`)
with 40-character commit SHAs plus a `# <version>` comment. Closes the
"action maintainer pushes a new tag pointing at compromised code"
attack vector.

**Requirements:** R4.

**Dependencies:** Unit 1 (dependabot is already up so bumps flow as
PRs once SHAs drift).

**Files:**
- Modify: `.github/workflows/tests.yml`
- Modify: `.github/workflows/publish.yml`

**Approach:**
- For each `uses: <action>@<tag>` line:
  1. Resolve the tag to a commit SHA via `gh api
     repos/<owner>/<name>/git/matching-refs/tags/<tag>` or the Actions
     Marketplace page.
  2. Rewrite as `uses: <action>@<sha>  # <tag>` — inline comment
     preserves reviewer readability and is the dependabot convention.
- Specifically:
  - `actions/checkout@v6` → pin to the v6.0.2 commit
  - `astral-sh/setup-uv@v8.1.0` → pin to the v8.1.0 commit (already
    pinned to a point release; swap the tag for its SHA)
  - `pypa/gh-action-pypi-publish@release/v1` → pin to the latest v1.x
    commit (e.g., v1.14.0 at time of planning — check fresh during
    implementation)
  - Any new actions added during this plan's execution
- Dependabot (Unit 1) is configured to keep these SHAs bumped with
  matching comment updates — no manual maintenance after this point.

**Patterns to follow:**
- GitHub's [security hardening guide](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-third-party-actions#using-third-party-actions) — the exact `uses: …@<sha>  # <tag>` format is their recommended convention.

**Test scenarios:**
- Happy path: CI on the PR is green — same job behavior, just different
  resolution path for the action code.
- Integration: dependabot emits a bump PR within a week that updates
  both the SHA and the comment. (Verify post-merge.)

**Verification:**
- All `uses:` lines in `.github/workflows/**` reference a 40-char SHA.
- `grep -rE 'uses:.*@(v[0-9]|release/)' .github/workflows/` returns no
  matches (or only first-party `actions/*` actions, if we choose to
  exempt those — decide during implementation).

---

- [ ] **Unit 5: `SECURITY.md` + `CODEOWNERS`**

**Goal:** Standard disclosure and ownership files for a public repo.
Enables GitHub's "Report a vulnerability" button and routes reviews to
the right person.

**Requirements:** R5.

**Dependencies:** None. Can land any time.

**Files:**
- Create: `SECURITY.md`
- Create: `.github/CODEOWNERS` (or `CODEOWNERS` at repo root — either
  location works; `.github/` is the convention)

**Approach:**
- `SECURITY.md` structure:
  - **Supported versions**: table listing which minor versions get
    security fixes. For dotgarden today: "latest `0.3.x` only."
  - **Reporting a vulnerability**: link to GitHub's private
    vulnerability reporting UI for the repo (enabled in repo settings →
    Security). Short note on expected response SLA.
  - **Scope**: what counts as a security issue (credential exposure,
    arbitrary code execution via a crafted `__registry__.yaml`,
    symlink-traversal) vs. what doesn't (DoS via `dotfile bootstrap`
    on a huge repo, user-side config mistakes).
- `CODEOWNERS` structure:
  - `* @andrewlook` as the default owner.
  - `/.github/workflows/** @andrewlook` — explicit for security-
    critical paths.
  - `/SECURITY.md @andrewlook`, `/.github/dependabot.yml @andrewlook`
    — same.

**Patterns to follow:**
- GitHub's [default SECURITY.md template](https://docs.github.com/en/code-security/getting-started/adding-a-security-policy-to-your-repository).
- Existing single-owner repos like [astral-sh/uv SECURITY.md](https://github.com/astral-sh/uv/blob/main/SECURITY.md) for reference.

**Test scenarios:**
- Integration: the GitHub Security tab shows the policy rendering
  correctly.
- Integration: GitHub shows a "CODEOWNERS rules met" check on a PR
  touching any file.
- Test expectation: none — docs + config, no behavioral change.

**Verification:**
- `SECURITY.md` renders as the repo's security policy (GitHub picks it
  up automatically from the root or `.github/`).
- Private vulnerability reporting is enabled in repo settings (requires
  a manual click; include a note in the PR description).

---

- [ ] **Unit 6: `zizmor` workflow audit + attestation verification docs**

**Goal:** Static-analyze the existing workflows for common CI
pitfalls; update the README / CHANGELOG to document how consumers can
verify PyPI artifact attestations.

**Requirements:** R6, R7.

**Dependencies:** Unit 4 (run zizmor against the final SHA-pinned
workflows).

**Files:**
- Modify: `.github/workflows/tests.yml` (add `zizmor` job, or split
  into `security.yml` alongside Unit 2's `audit` job)
- Modify: `README.md` (add "Verifying release attestations" section)
- Modify: `CHANGELOG.md` (note that every release from this version
  forward ships PEP 740 attestations)

**Approach:**
- Add a CI job that runs `uvx zizmor .` (or the
  `zizmors/zizmor-action@<sha>` action). Treat medium-severity findings
  as warnings, high-severity as failures. Configure with a minimal
  `.zizmor.yml` if needed to suppress known-safe patterns.
- Run `zizmor` locally first to see the baseline; resolve anything
  high-severity before landing the CI job.
- README addition: a short "Verify a release's provenance" section
  showing `gh attestation verify dist/dotgarden-X.Y.Z.tar.gz --repo
  andrewlook/dotgarden`. Reference the PEP 740 standard.
- Confirm the publish workflow is using `pypa/gh-action-pypi-publish`
  v1.11.0+ (it is — `release/v1` currently floats to v1.14.0 at time
  of planning). After Unit 4, it's pinned to a specific SHA, so this
  just requires picking a SHA at or past v1.11.0.

**Patterns to follow:**
- [`zizmor` documentation](https://woodruffw.github.io/zizmor/) — their
  recommended CI integration shape.
- [GitHub's `gh attestation verify` docs](https://cli.github.com/manual/gh_attestation_verify) for the verification command.

**Test scenarios:**
- Happy path: `uvx zizmor .` exits 0 on the branch.
- Error path: the CI job fails loudly when a workflow change introduces
  a high-severity finding (verified via dry-run or a deliberate bad
  workflow on a throwaway branch).
- Integration: README's verification command works against a real
  published artifact. Must wait for the first published tag to actually
  verify — mark this check as deferred in the PR description until the
  first release tag lands.

**Verification:**
- `zizmor` CI job green on the PR.
- README renders the new section correctly.
- CHANGELOG has a "Security" subsection under the next release
  heading mentioning attestations.

## System-Wide Impact

- **Interaction graph:** CI touches — every PR triggers more work
  (`audit`, `zizmor`, potentially the ruff `S` rules in the existing
  `lint` step if a separate hook exists). Expect a ~10-15s latency
  increase per PR.
- **Error propagation:** A new CVE in a transitive dependency could
  block merges until dependabot's fix PR lands. Acceptable tradeoff;
  the alternative is unaudited exposure.
- **State lifecycle risks:** None meaningful — no runtime code changes,
  all config/CI.
- **API surface parity:** `dotfile` CLI surface unchanged.
- **Integration coverage:** Existing integration tests continue to run;
  new CI jobs add coverage, not replace.
- **Unchanged invariants:** Trusted publishing, `environment: pypi`
  gate, and the `uv.lock` lockfile are preserved as-is — they already
  do the right thing.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Dependabot PR noise fatigues maintainer, bumps stall | Weekly (not daily) schedule; `open-pull-requests-limit: 5`; grouped bumps via dependabot's `groups:` config can be added in a follow-up if volume becomes an issue. |
| `pip-audit` flags a CVE with no fix available, blocking merges | Use `--ignore-vuln <GHSA-ID>` with a comment linking to the upstream issue, + revisit weekly. Document the escape hatch in the workflow file. |
| `zizmor` flags `permissions: id-token: write` as a finding | Expected. Suppress via `.zizmor.yml` or `# zizmor: ignore-rule=<id>` — the trusted-publishing pattern is a known-safe case. |
| Ruff `S` rules flag legitimate patterns in the CLI (e.g., `os.path` join with user input in `symlinks.py`) | Triage during Unit 3; `# noqa: S…` with a rationale where appropriate. |
| SHA-pinning breaks when a dependabot bump references a SHA that turns out to be malicious | Rare but real. GitHub's review workflow catches this — dependabot PRs aren't auto-merged; reviewer sees the diff including the action's own changes. |
| Private vulnerability reporting not auto-enabled | Must flip the repo setting manually (Repo → Settings → Security → Private vulnerability reporting → Enable). Include in the PR description checklist. |
| CI time budget grows meaningfully | The `audit` + `zizmor` jobs run in parallel with existing `unit` / `integration` jobs; net wall-clock increase should be <30s. Monitor after landing. |

## Documentation / Operational Notes

- **SECURITY.md** lands with the initial plan; version supported list
  needs updating on each minor bump — add a CHANGELOG reminder.
- **CHANGELOG.md** "Security" subsection under the next release starts
  the habit of calling out security-relevant changes per release.
- **README.md** gets a "Verifying release attestations" section (part
  of Unit 6). Keep it ~5-10 lines; link to the PEP 740 canonical docs
  for depth.
- **AGENTS.md** (dotgarden) gets a short "Supply chain" paragraph under
  "Things to avoid" reiterating: don't introduce new runtime deps
  without discussion, don't revert SHA pins, don't edit `dependabot.yml`
  without understanding the schedule implications.

## Sources & References

- External: [bernat.tech — Securing the Python Supply Chain](https://bernat.tech/posts/securing-python-supply-chain/)
- External: [PyPA gh-action-pip-audit](https://github.com/pypa/gh-action-pip-audit)
- External: [`zizmor` — GitHub Actions static analyzer](https://woodruffw.github.io/zizmor/)
- External: [PEP 740 — Index support for digital attestations](https://peps.python.org/pep-0740/)
- External: [GitHub: using third-party actions securely](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-third-party-actions)
- Related code: `.github/workflows/publish.yml`, `.github/workflows/tests.yml`,
  `ruff.toml`, `pyproject.toml`
- Related PRs: andrewlook/dotgarden#8 (recent `submodules: true` checkout
  fix — precedent for this plan's CI-hardening pattern)
