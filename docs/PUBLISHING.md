# Publishing `langchain-islo` to PyPI

The maintainer's guidance on `langchain-ai/deepagents#3777` is: **ship as a
standalone PyPI package**, then open a docs PR. This is the publish half.

## Preconditions

- [ ] Repo created (suggested: `islo-labs/langchain-islo`) with this package at root.
- [ ] PyPI account + project owned by the Islo/Incredibuild org.
- [ ] CI green: `make lint` and `make test` (unit tests run offline).

## Build & check

```bash
uv build                      # or: python -m build
uvx twine check dist/*
```

## Test it from a clean env (optional but recommended)

```bash
python -m venv /tmp/islo-check && . /tmp/islo-check/bin/activate
pip install dist/langchain_islo-*.whl
python -c "from langchain_islo import IsloSandbox, IsloProvider; print('ok')"
```

## Publish

Trusted publishing (recommended) via GitHub Actions, or manually:

```bash
uvx twine upload dist/*
```

## Live integration test (needs a real account)

```bash
export ISLO_API_KEY="ak_..."
make integration_test
```

This runs the deepagents standard suite (`SandboxIntegrationTests`) against a
real Islo sandbox.

## After publishing

1. Confirm `pip install langchain-islo` works from PyPI.
2. Open the docs PR — see [`DOCS_PR.md`](./DOCS_PR.md).
3. Post the follow-up on issue #3777 — see [`issue-reply.md`](./issue-reply.md).
