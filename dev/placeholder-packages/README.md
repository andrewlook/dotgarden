# Typosquat placeholder packages

These packages exist to claim names on PyPI that are visually close to
[`dotgarden`](https://pypi.org/project/dotgarden/), so nobody else can ship a
working package under a typo'd name and trick users who fat-finger
`pip install`.

Each placeholder is a three-file Python package pinned at `0.0.1` forever.
Importing the installed package raises `RuntimeError` with a message
pointing at the real `dotgarden`.

## Coverage

| Directory     | PyPI name     | Typo covered             | Status                                          |
|---------------|---------------|--------------------------|-------------------------------------------------|
| `dot-garden/` | `dot-garden`  | hyphen / underscore      | Blocked by PyPI's name-similarity check — no placeholder needed (nobody can register it) |
| `dotgardens/` | `dotgardens`  | pluralization            | Published as placeholder at <https://pypi.org/project/dotgardens/> |
| `dotgardn/`   | `dotgardn`    | missing "e"              | Published as placeholder at <https://pypi.org/project/dotgardn/> |

### Note on hyphen/underscore

Under [PEP 503 name
normalization](https://peps.python.org/pep-0503/#normalized-names), PyPI
treats `dot-garden`, `dot_garden`, `dot.garden`, `Dot-Garden`, etc. as the
**same** project. Additionally, PyPI's similarity check rejects new
registrations when the normalized name collides with an existing project
using only typographic separators — so `dot-garden` / `dot_garden` are
auto-defended once `dotgarden` exists, and the scaffolding under
`dot-garden/` is kept only as documentation of the attempt.

## Publishing

These publish to **real PyPI**, not TestPyPI. Use the one-time publish
script from the repo root:

```bash
dev/publish-placeholders
```

The script reads creds from `~/.pypirc` (`[pypi]` section) and uploads each
placeholder via `twine`. Safe to re-run; PyPI rejects duplicate uploads of
an existing `name==version`.
