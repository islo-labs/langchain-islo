# Changelog

## 0.0.1

Initial release.

- `IsloSandbox`: a `deepagents` `BaseSandbox` backend for [Islo](https://islo.dev),
  implementing `execute()`, `upload_files()`, `download_files()`, and `id`.
  Filesystem tools (`ls`, `read`, `write`, `edit`, `glob`, `grep`) are inherited
  from `BaseSandbox`.
- `IsloProvider`: optional lifecycle helper (`get_or_create()` / `delete()`).
- Validated against the `deepagents` `SandboxIntegrationTests` standard suite.
