# Changelog

## 0.0.4

- Standardized the backend interface: the poll knob is now
  `sync_polling_interval` (a fixed delay **or** a callable of elapsed seconds),
  and `execute()` formats stderr as a `<stderr>...</stderr>` block appended to
  stdout. (`poll_interval` is renamed to `sync_polling_interval`.)

## 0.0.3

- `download_files`: when a download fails, classify the path inside the sandbox
  so a directory is reported as `is_directory` and a missing path as
  `file_not_found`, regardless of the provider's HTTP status. Fixes the
  `SandboxIntegrationTests` directory-download case against live Islo, which
  returns a generic `500` for directory downloads.

## 0.0.2

- `execute()` now polls the Islo exec result directly instead of using the SDK's
  `exec_and_wait` helper, so the real `exit_code` and the `truncated` flag are
  preserved (the helper dropped both). stderr is kept on its own line rather than
  glued onto stdout. Adds 5xx poll-retry tolerance.
- Switched tooling to **uv-first** (uv.lock, uv-based CI).
- Documented the sandbox image requirement (`python3` + GNU `grep`), e.g.
  `python:3.12-slim`, needed by the inherited filesystem tools.

## 0.0.1

Initial release.

- `IsloSandbox`: a `deepagents` `BaseSandbox` backend for [Islo](https://islo.dev),
  implementing `execute()`, `upload_files()`, `download_files()`, and `id`.
  Filesystem tools (`ls`, `read`, `write`, `edit`, `glob`, `grep`) are inherited
  from `BaseSandbox`.
- `IsloProvider`: optional lifecycle helper (`get_or_create()` / `delete()`).
- Validated against the `deepagents` `SandboxIntegrationTests` standard suite.
