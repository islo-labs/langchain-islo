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
    file bytes, so byte transfer is performed against the sandbox files endpoint
    on the *compute* base URL, reusing the client's resolved auth headers (the
    same approach used by the Islo SDK's own ``islo.custom.files`` helpers).
"""

from __future__ import annotations

import io
import posixpath
import shlex
from typing import TYPE_CHECKING

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
from islo.custom.exec import exec_and_wait_sync

if TYPE_CHECKING:
    from islo import Islo
    from islo.types import SandboxResponse

# Islo executes an argv list, not a shell line. deepagents emits shell command
# strings (pipes, redirects, here-docs), so each command is run through `sh -c`.
_SHELL: tuple[str, str] = ("/bin/sh", "-c")

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
        sandbox = client.sandboxes.create_sandbox(image="ubuntu:24.04")
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
        poll_interval: float = 0.5,
        http_timeout: float = 60.0,
    ) -> None:
        """Wrap an existing Islo sandbox.

        Args:
            client: An authenticated ``islo.Islo`` client.
            sandbox: An Islo ``SandboxResponse`` (e.g. from
                ``client.sandboxes.create_sandbox(...)``). Sandbox operations are
                keyed by ``sandbox.name``.
            timeout: Default command timeout in seconds used by ``execute()``
                when no explicit timeout is given. A value of ``0`` waits
                indefinitely.
            poll_interval: Seconds between polls of the exec result while waiting
                for a command to finish.
            http_timeout: Per-request timeout in seconds for file
                upload/download transfers.
        """
        self._client = client
        self._sandbox = sandbox
        self._default_timeout = timeout
        self._poll_interval = poll_interval
        self._http_timeout = http_timeout

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
        """
        effective_timeout = self._default_timeout if timeout is None else timeout
        # The exec helper treats `timeout=None` as "poll indefinitely", which is
        # the semantic deepagents assigns to a timeout of 0.
        helper_timeout = None if effective_timeout == 0 else float(effective_timeout)

        result = exec_and_wait_sync(
            self._client,
            self._sandbox.name,
            [_SHELL[0], _SHELL[1], command],
            timeout=helper_timeout,
            poll_interval=self._poll_interval,
        )

        if result.timed_out:
            return ExecuteResponse(
                output=f"Command timed out after {effective_timeout} seconds",
                exit_code=_TIMEOUT_EXIT_CODE,
                truncated=False,
            )

        output = result.stdout
        if result.stderr:
            output = f"{output}{result.stderr}" if output else result.stderr

        return ExecuteResponse(
            output=output,
            exit_code=result.exit_code,
            truncated=False,
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

        base_url = self._compute_base_url()
        headers = self._auth_headers()
        with httpx.Client(timeout=self._http_timeout) as http:
            for idx, path, content in pending:
                filename = posixpath.basename(path) or "file"
                try:
                    response = http.post(
                        f"{base_url}/sandboxes/{self._sandbox.name}/files",
                        params={"path": path},
                        headers=headers,
                        files={"file": (filename, io.BytesIO(content))},
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    responses[idx] = FileUploadResponse(
                        path=path,
                        error=_map_http_status(exc.response.status_code),
                    )
                except httpx.HTTPError as exc:  # network/timeout errors
                    responses[idx] = FileUploadResponse(path=path, error=str(exc))
                else:
                    responses[idx] = FileUploadResponse(path=path, error=None)

        return [r for r in responses if r is not None]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from the sandbox.

        Supports partial success: per-file failures are returned as errors on the
        corresponding ``FileDownloadResponse`` rather than raised.
        """
        responses: list[FileDownloadResponse] = []
        base_url = self._compute_base_url()
        headers = self._auth_headers()

        with httpx.Client(timeout=self._http_timeout) as http:
            for path in paths:
                if not path.startswith("/"):
                    responses.append(
                        FileDownloadResponse(
                            path=path, content=None, error=INVALID_PATH
                        )
                    )
                    continue
                try:
                    response = http.get(
                        f"{base_url}/sandboxes/{self._sandbox.name}/files",
                        params={"path": path},
                        headers=headers,
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    responses.append(
                        FileDownloadResponse(
                            path=path,
                            content=None,
                            error=_map_http_status(exc.response.status_code),
                        )
                    )
                except httpx.HTTPError as exc:
                    responses.append(
                        FileDownloadResponse(path=path, content=None, error=str(exc))
                    )
                else:
                    responses.append(
                        FileDownloadResponse(
                            path=path, content=response.content, error=None
                        )
                    )

        return responses

    # -- internals -----------------------------------------------------------

    def _compute_base_url(self) -> str:
        """Resolve the Islo *compute* base URL hosting the exec/files endpoints."""
        return self._client._client_wrapper.get_environment().compute.rstrip("/")

    def _auth_headers(self) -> dict[str, str]:
        """Resolve fresh auth headers (honors token refresh) for raw requests."""
        return self._client._client_wrapper.get_headers()


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
