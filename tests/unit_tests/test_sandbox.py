from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from islo.core.api_error import ApiError

from langchain_islo.sandbox import IsloSandbox, _map_http_status

TIMEOUT_EXIT_CODE = 124


def _exec_result(
    *,
    status: str = "completed",
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = 0,
    truncated: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        truncated=truncated,
    )


def _make_sandbox() -> tuple[IsloSandbox, MagicMock]:
    client = MagicMock()
    client._client_wrapper.get_environment.return_value = SimpleNamespace(
        compute="https://ca.compute.islo.dev",
        control="https://api.islo.dev",
    )
    client._client_wrapper.get_headers.return_value = {
        "Authorization": "Bearer ak_test"
    }
    sandbox = SimpleNamespace(id="sb-123", name="my-sandbox", status="running")
    return IsloSandbox(client=client, sandbox=sandbox), client


def test_id_and_name() -> None:
    sb, _ = _make_sandbox()
    assert sb.id == "sb-123"
    assert sb.name == "my-sandbox"


def test_execute_combines_stdout_and_stderr() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.return_value = _exec_result(
        stdout="out", stderr="err", exit_code=0
    )
    result = sb.execute("echo hi")

    # stderr is kept on its own line (never glued onto stdout).
    assert result.output == "out\nerr"
    assert result.exit_code == 0
    assert result.truncated is False

    # Command must be wrapped in a shell so pipes/redirects/here-docs work.
    args, kwargs = client.sandboxes.exec_in_sandbox.call_args
    assert args[0] == "my-sandbox"
    assert kwargs["command"] == ["/bin/sh", "-c", "echo hi"]


def test_execute_stdout_only() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.return_value = _exec_result(stdout="hello")
    result = sb.execute("echo hello")
    assert result.output == "hello"


def test_execute_propagates_truncated_flag() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.return_value = _exec_result(
        stdout="x" * 100, truncated=True
    )
    result = sb.execute("cat big")
    assert result.truncated is True


def test_execute_exit_code_none_completed_defaults_zero() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.return_value = _exec_result(
        status="completed", exit_code=None
    )
    assert sb.execute("true").exit_code == 0


def test_execute_exit_code_none_failed_defaults_nonzero() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.return_value = _exec_result(
        status="failed", exit_code=None
    )
    assert sb.execute("false").exit_code == 1


def test_execute_polls_until_terminal() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.side_effect = [
        _exec_result(status="running", exit_code=None),
        _exec_result(status="completed", stdout="done"),
    ]
    with patch("langchain_islo.sandbox.time.sleep"):
        result = sb.execute("slow")
    assert result.output == "done"
    assert client.sandboxes.get_exec_result.call_count == 2


def test_execute_retries_on_server_error() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.side_effect = [
        ApiError(status_code=503, headers={}, body="boom"),
        _exec_result(status="completed", stdout="ok"),
    ]
    with patch("langchain_islo.sandbox.time.sleep"):
        result = sb.execute("x")
    assert result.output == "ok"


def test_execute_timeout_maps_to_124() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.return_value = _exec_result(
        status="running", exit_code=None
    )
    with (
        patch("langchain_islo.sandbox.time.monotonic", side_effect=[0.0, 11.0]),
        patch("langchain_islo.sandbox.time.sleep"),
    ):
        result = sb.execute("sleep 999", timeout=5)
    assert result.exit_code == TIMEOUT_EXIT_CODE
    assert "timed out" in result.output


def test_execute_timeout_zero_polls_until_terminal() -> None:
    sb, client = _make_sandbox()
    client.sandboxes.exec_in_sandbox.return_value = SimpleNamespace(exec_id="e1")
    client.sandboxes.get_exec_result.return_value = _exec_result(stdout="ok")
    result = sb.execute("echo hi", timeout=0)
    assert result.output == "ok"


def test_upload_rejects_relative_path() -> None:
    sb, _ = _make_sandbox()
    responses = sb.upload_files([("relative/path.txt", b"data")])
    assert len(responses) == 1
    assert responses[0].path == "relative/path.txt"
    assert responses[0].error == "invalid_path"


def test_upload_success_creates_parents_and_posts() -> None:
    sb, client = _make_sandbox()
    response = MagicMock()
    response.raise_for_status.return_value = None
    client._client_wrapper.httpx_client.request.return_value = response

    with patch.object(sb, "execute") as mock_execute:
        responses = sb.upload_files([("/workspace/app.py", b"print('hi')")])

    assert responses[0].error is None
    # mkdir -p for the parent directory should have been issued.
    mkdir_cmd = mock_execute.call_args[0][0]
    assert mkdir_cmd.startswith("mkdir -p ")
    assert "/workspace" in mkdir_cmd
    # The request goes through the SDK's HTTP client to the files endpoint.
    args, kwargs = client._client_wrapper.httpx_client.request.call_args
    assert args[0] == "sandboxes/my-sandbox/files"
    assert kwargs["method"] == "POST"
    assert kwargs["params"] == {"path": "/workspace/app.py"}
    assert "file" in kwargs["files"]


def test_upload_partial_success() -> None:
    sb, client = _make_sandbox()
    ok = MagicMock()
    ok.raise_for_status.return_value = None
    bad_response = MagicMock(status_code=403)
    err = httpx.HTTPStatusError("forbidden", request=MagicMock(), response=bad_response)
    bad = MagicMock()
    bad.raise_for_status.side_effect = err
    client._client_wrapper.httpx_client.request.side_effect = [ok, bad]

    with patch.object(sb, "execute"):
        responses = sb.upload_files([("/ok.txt", b"a"), ("/denied.txt", b"b")])

    assert responses[0].error is None
    assert responses[1].error == "permission_denied"


def test_download_success_returns_bytes() -> None:
    sb, client = _make_sandbox()
    response = MagicMock(content=b"file-bytes")
    response.raise_for_status.return_value = None
    client._client_wrapper.httpx_client.request.return_value = response

    responses = sb.download_files(["/workspace/app.py"])

    assert responses[0].content == b"file-bytes"
    assert responses[0].error is None
    args, kwargs = client._client_wrapper.httpx_client.request.call_args
    assert args[0] == "sandboxes/my-sandbox/files"
    assert kwargs["method"] == "GET"


def test_download_not_found() -> None:
    sb, client = _make_sandbox()
    missing = MagicMock(status_code=404)
    err = httpx.HTTPStatusError("nope", request=MagicMock(), response=missing)
    response = MagicMock()
    response.raise_for_status.side_effect = err
    client._client_wrapper.httpx_client.request.return_value = response

    # On failure the path is classified in the sandbox; here it doesn't exist.
    with patch.object(sb, "execute", return_value=SimpleNamespace(output="missing")):
        responses = sb.download_files(["/missing.txt"])

    assert responses[0].content is None
    assert responses[0].error == "file_not_found"


def test_download_is_directory_via_500() -> None:
    # Real Islo returns HTTP 500 for a directory download; we classify in-sandbox.
    sb, client = _make_sandbox()
    resp500 = MagicMock(status_code=500)
    err = httpx.HTTPStatusError("boom", request=MagicMock(), response=resp500)
    response = MagicMock()
    response.raise_for_status.side_effect = err
    client._client_wrapper.httpx_client.request.return_value = response

    with patch.object(sb, "execute", return_value=SimpleNamespace(output="dir")):
        responses = sb.download_files(["/work/somedir"])

    assert responses[0].content is None
    assert responses[0].error == "is_directory"


def test_download_rejects_relative_path() -> None:
    sb, _ = _make_sandbox()
    responses = sb.download_files(["relative.txt"])
    assert responses[0].error == "invalid_path"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (404, "file_not_found"),
        (403, "permission_denied"),
        (400, "invalid_path"),
        (409, "is_directory"),
        (500, "http_500"),
    ],
)
def test_map_http_status(status: int, expected: str) -> None:
    assert _map_http_status(status) == expected
