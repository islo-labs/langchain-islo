"""Islo sandbox backend implementation.

[`IsloSandbox`][langchain_islo.sandbox.IsloSandbox] wraps an Islo sandbox
(https://islo.dev) and conforms to deepagents'
[`SandboxBackendProtocol`][deepagents.backends.protocol.SandboxBackendProtocol].

It subclasses [`BaseSandbox`][deepagents.backends.sandbox.BaseSandbox], so the
filesystem tools (``ls``, ``read``, ``write``, ``edit``, ``glob``, ``grep``) are
provided for free on top of three primitives implemented here:

- ``execute`` -- run a shell command via Islo's exec API (submit + poll).
- ``upload_files`` / ``download_files`` -- transfer raw bytes over Islo's
  sandbox files endpoint.

Notes:
    The deepagents base class sends *full shell command strings* (pipes,
    redirects, here-docs). Islo's ``exec_in_sandbox`` executes an ``argv`` list
    directly without a shell, so every command is wrapped in
    ``["/bin/sh", "-c", command]``.

    Islo's generated ``upload_file`` / ``download_file`` SDK methods do not carry
    file bytes, so byte transfer is driven through the SDK's own HTTP client
    (``client._client_wrapper.httpx_client``) against the sandbox files endpoint,
    reusing the SDK's auth, base URL, retry, and timeout handling.
"""

from __future__ import annotations

import posixpath
import shlex
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import httpx
from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    INVALID_PATH,
    IS_DIRECTORY,
    PERMISSION_DENIED,
    ExecuteResponse,
    FileDownloadResponse,
    FileOperationError,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox
from islo.core.api_error import ApiError

if TYPE_CHECKING:
    from islo import Islo
    from islo.types import ExecResultResponse, SandboxResponse

# Mirrors the DaytonaSandbox interface: a fixed delay, or a callable that
# receives elapsed execution time (seconds) and returns the next poll delay.
SyncPollingInterval = float | Callable[[float], float]
PollingStrategy = Callable[[float], float]

# Islo executes an argv list, not a shell line. deepagents emits shell command
# strings (pipes, redirects, here-docs), so each command is run through `sh -c`.
_SHELL: tuple[str, str] = ("/bin/sh", "-c")

# Exec is asynchronous server-side: submit returns an exec_id, then we poll the
# result until it reaches a terminal status.
_TERMINAL_STATUSES = frozenset({"completed", "failed", "timeout"})
_MAX_CONSECUTIVE_POLL_ERRORS = 5

_TIMEOUT_EXIT_CODE = 124
"""Exit code returned when a command exceeds its timeout (matches `timeout(1)`)."""

_HTTP_NOT_FOUND = 404
_HTTP_FORBIDDEN = 403
_HTTP_BAD_REQUEST = 400


class IsloSandbox(BaseSandbox):
    """Islo sandbox backend conforming to ``SandboxBackendProtocol``.

    Inherits all filesystem operations from ``BaseSandbox`` and implements
    ``execute``, ``upload_files``, ``download_files``, and ``id`` using the Islo
    Python SDK (https://github.com/islo-labs/python-sdk).

    Example:
        ```python
        from islo import Islo
        from langchain_islo import IsloSandbox

        client = Islo()  # reads ISLO_API_KEY
        sandbox = client.sandboxes.create_sandbox(image="python:3.12-slim")
        backend = IsloSandbox(client=client, sandbox=sandbox)

        result = backend.execute("echo hello")
        print(result.output)  # "hello"
        ```
    """

    def __init__(
        self,
        *,
        client: Islo,
        sandbox: SandboxResponse,
        timeout: int = 30 * 60,
        sync_polling_interval: SyncPollingInterval = 0.5,
        http_timeout: int = 60,
    ) -> None:
        """Wrap an existing Islo sandbox.

        Mirrors the ``DaytonaSandbox`` interface (``timeout`` +
        ``sync_polling_interval``), with an extra ``client`` because Islo's
        ``SandboxResponse`` is a data object — operations live on
        ``client.sandboxes`` and are keyed by ``sandbox.name``.

        Args:
            client: An authenticated ``islo.Islo`` client.
            sandbox: An Islo ``SandboxResponse`` (e.g. from
                ``client.sandboxes.create_sandbox(...)``).
            timeout: Default command timeout in seconds used by ``execute()``
                when no explicit timeout is given. A value of ``0`` waits
                indefinitely.
            sync_polling_interval: Delay in seconds between polls of the exec
                result, or a callable that receives elapsed execution time in
                seconds and returns the next polling delay.
            http_timeout: Per-request timeout in seconds for file
                upload/download transfers.
        """
        self._client = client
        self._sandbox = sandbox
        self._default_timeout = timeout
        self._http_timeout = http_timeout
        polling_strategy: PollingStrategy
        if callable(sync_polling_interval):
            polling_strategy = cast("PollingStrategy", sync_polling_interval)
        else:

            def polling_strategy(_elapsed: float) -> float:
                return sync_polling_interval

        self._sync_polling_interval = polling_strategy

    @property
    def id(self) -> str:
        """Return the Islo sandbox id."""
        return self._sandbox.id

    @property
    def name(self) -> str:
        """Return the Islo sandbox name (the key most Islo APIs use)."""
        return self._sandbox.name

    # -- command execution ---------------------------------------------------

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Execute a shell command inside the sandbox.

        Args:
            command: Full shell command string to execute.
            timeout: Maximum seconds to wait for completion. If ``None``, uses
                the backend's default timeout. A value of ``0`` waits
                indefinitely.

        Returns:
            ``ExecuteResponse`` with combined stdout/stderr, the exit code, and a
            truncation flag.

        Notes:
            We poll the Islo exec result directly (rather than via the SDK's
            ``exec_and_wait`` helper) so the real ``exit_code`` and the
            ``truncated`` flag are preserved — the helper drops both.
        """
        effective_timeout = self._default_timeout if timeout is None else timeout

        sandboxes = self._client.sandboxes
        started_at = time.monotonic()
        submission = sandboxes.exec_in_sandbox(
            self._sandbox.name,
            command=[_SHELL[0], _SHELL[1], command],
        )
        exec_id = submission.exec_id

        consecutive_errors = 0
        while True:
            elapsed = time.monotonic() - started_at
            # A timeout of 0 means "wait indefinitely" (matches DaytonaSandbox).
            if effective_timeout != 0 and elapsed >= effective_timeout:
                return ExecuteResponse(
                    output=f"Command timed out after {effective_timeout} seconds",
                    exit_code=_TIMEOUT_EXIT_CODE,
                    truncated=False,
                )
            try:
                result = sandboxes.get_exec_result(self._sandbox.name, exec_id)
                consecutive_errors = 0
            except ApiError as exc:
                status = exc.status_code
                if (
                    status is not None
                    and status >= 500  # noqa: PLR2004  # transient server error
                    and consecutive_errors < _MAX_CONSECUTIVE_POLL_ERRORS
                ):
                    consecutive_errors += 1
                    time.sleep(self._sync_polling_interval(elapsed))
                    continue
                raise
            if result.status in _TERMINAL_STATUSES:
                return self._to_execute_response(result)
            time.sleep(self._sync_polling_interval(elapsed))

    @staticmethod
    def _to_execute_response(result: ExecResultResponse) -> ExecuteResponse:
        """Map an Islo exec result into deepagents' ``ExecuteResponse``.

        Matches ``DaytonaSandbox``'s output convention: stdout, with any stderr
        appended in a ``<stderr>...</stderr>`` block. The BaseSandbox file-op
        scripts redirect stderr server-side, so ``stderr`` is empty for those and
        their single-line JSON on stdout is never disturbed.
        """
        output = result.stdout or ""
        stderr = result.stderr or ""
        if stderr.strip():
            output += f"\n<stderr>{stderr.strip()}</stderr>"

        exit_code = result.exit_code
        if exit_code is None:
            # Islo may omit the code on a terminal status; infer a sane value.
            exit_code = 0 if result.status == "completed" else 1

        return ExecuteResponse(
            output=output,
            exit_code=exit_code,
            truncated=bool(getattr(result, "truncated", False)),
        )

    # -- file transfer -------------------------------------------------------

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files into the sandbox.

        Supports partial success: per-file failures are returned as errors on the
        corresponding ``FileUploadResponse`` rather than raised. Parent
        directories are created before upload.
        """
        responses: list[FileUploadResponse | None] = []
        pending: list[tuple[int, str, bytes]] = []

        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error=INVALID_PATH))
                continue
            responses.append(None)  # placeholder, filled after transfer
            pending.append((len(responses) - 1, path, content))

        if not pending:
            return [r for r in responses if r is not None]

        # Ensure parent directories exist (upload contract requirement).
        parents = sorted(
            {posixpath.dirname(p) for _, p, _ in pending if posixpath.dirname(p)}
        )
        if parents:
            quoted = " ".join(shlex.quote(d) for d in parents)
            self.execute(f"mkdir -p {quoted}")

        for idx, path, content in pending:
            filename = posixpath.basename(path) or "file"
            try:
                response = self._files_request(
                    "POST", path, files={"file": (filename, content)}
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                responses[idx] = FileUploadResponse(
                    path=path,
                    # Protocol permits a backend-specific error string.
                    error=_map_http_status(exc.response.status_code),  # ty: ignore[invalid-argument-type]
                )
            except httpx.HTTPError as exc:  # network/timeout errors
                responses[idx] = FileUploadResponse(path=path, error=str(exc))  # ty: ignore[invalid-argument-type]
            else:
                responses[idx] = FileUploadResponse(path=path, error=None)

        return [r for r in responses if r is not None]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from the sandbox.

        Supports partial success: per-file failures are returned as errors on the
        corresponding ``FileDownloadResponse`` rather than raised.
        """
        responses: list[FileDownloadResponse] = []

        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error=INVALID_PATH)
                )
                continue
            try:
                response = self._files_request("GET", path)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Protocol permits a backend-specific error string.
                err = self._classify_download_error(path, exc.response.status_code)
                responses.append(
                    FileDownloadResponse(path=path, content=None, error=err)  # ty: ignore[invalid-argument-type]
                )
            except httpx.HTTPError as exc:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error=str(exc))  # ty: ignore[invalid-argument-type]
                )
            else:
                responses.append(
                    FileDownloadResponse(
                        path=path, content=response.content, error=None
                    )
                )

        return responses

    # -- internals -----------------------------------------------------------

    def _classify_download_error(
        self, path: str, status_code: int
    ) -> FileOperationError | str:
        """Disambiguate a failed download by inspecting the path in the sandbox.

        Islo returns a generic ``500`` when asked to download a directory, so the
        HTTP status alone can't distinguish ``is_directory`` from a real server
        error. We probe the sandbox to report the most actionable error.
        """
        quoted = shlex.quote(path)
        probe = self.execute(
            f"if [ -d {quoted} ]; then echo dir; "
            f"elif [ -e {quoted} ]; then echo file; else echo missing; fi"
        )
        verdict = probe.output.strip().splitlines()[-1] if probe.output.strip() else ""
        if verdict == "dir":
            return IS_DIRECTORY
        if verdict == "missing":
            return FILE_NOT_FOUND
        return _map_http_status(status_code)

    def _files_request(
        self,
        method: str,
        path: str,
        *,
        files: dict | None = None,
    ) -> httpx.Response:
        """Call the sandbox files endpoint via the Islo SDK's HTTP client.

        Reuses the SDK's configured transport (auth headers, base URL, retries,
        timeout) instead of issuing raw requests. The generated
        ``upload_file``/``download_file`` SDK methods don't carry file bytes, so
        we drive the same endpoint through ``client._client_wrapper.httpx_client``.
        """
        wrapper = self._client._client_wrapper
        return wrapper.httpx_client.request(
            f"sandboxes/{self._sandbox.name}/files",
            method=method,
            base_url=wrapper.get_environment().compute,
            params={"path": path},
            files=files,
            request_options={"timeout_in_seconds": self._http_timeout},
        )


def _map_http_status(status_code: int) -> FileOperationError | str:
    """Map an HTTP status to a standardized ``FileOperationError`` literal."""
    if status_code == _HTTP_NOT_FOUND:
        return FILE_NOT_FOUND
    if status_code == _HTTP_FORBIDDEN:
        return PERMISSION_DENIED
    if status_code == _HTTP_BAD_REQUEST:
        return INVALID_PATH
    if status_code == 409:  # noqa: PLR2004  # conflict: path is a directory
        return IS_DIRECTORY
    return f"http_{status_code}"
