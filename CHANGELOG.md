# Changelog

## 0.0.2

- `execute()` now polls the Islo exec result directly instead of using the SDK's
  `exec_and_wait` helper, so the real `exit_code` and the `truncated` flag are
  preserved (the helper dropped both). stderr is kept on its own line rather than
  glued onto stdout. Adds 5xx poll-retry tolerance.
- Switched tooling to **uv-first** (uv.lock, uv-based CI).
- Integration suite now defaults to the `python:3.12-slim` image (ships
  `python3`, `python`, and GNU `grep`, which the standard suite requires).

## 0.0.1

Initial release.

- `IsloSandbox`: a `deepagents` `BaseSandbox` backend for [Islo](https://islo.dev),
  implementing `execute()`, `upload_files()`, `download_files()`, and `id`.
  Filesystem tools (`ls`, `read`, `write`, `edit`, `glob`, `grep`) are inherited
  from `BaseSandbox`.
- `IsloProvider`: optional lifecycle helper (`get_or_create()` / `delete()`).
- Validated against the `deepagents` `SandboxIntegrationTests` standard suite.
