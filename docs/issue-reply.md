# Draft reply for langchain-ai/deepagents#3777

> Post this once the package is on PyPI and the docs PR is open. It (a) confirms
> you followed their standalone-package guidance and (b) gives the feedback
> `mdrxy` explicitly asked for on recommending community integrations.

---

Thanks @mdrxy — totally understand the maintenance/security rationale for not
taking new sandboxes in-tree.

We went the standalone route as suggested:

- 📦 Published **`langchain-islo`** to PyPI: https://pypi.org/project/langchain-islo/
- It subclasses `BaseSandbox` and implements `execute()` / `upload_files()` /
  `download_files()` / `id`, and passes the `SandboxIntegrationTests` standard
  suite (`tests/integration_tests/test_sandbox.py`), per the
  [contributing guide](https://docs.langchain.com/oss/python/contributing/implement-langchain#sandboxes).
- 📄 Docs PR adding the integration page: <link to langchain-ai/docs PR>

On your open question about how to surface community integration packages — a
few ideas from the implementer's seat:

1. **A "Community" section on the Sandboxes index page** (separate from the
   first-party cards) that links out to third-party PyPI packages + their docs.
   Zero maintenance for you, discoverable for users.
2. **An optional entry-point / plugin hook** so `deepagents-cli --sandbox <name>`
   can discover installed third-party backends without a hardcoded `choices`
   list in `sandbox_factory.py`. Today adding a CLI sandbox name requires an
   in-tree edit, which is the one thing a standalone package *can't* do — an
   entry-point group (e.g. `deepagents.sandboxes`) would close that gap.
3. **A lightweight "verified" badge** keyed off the standard test suite passing
   in the package's own CI, so users can tell which community packages meet the
   contract.

Happy to prototype (1) or (2) as a PR if useful.
