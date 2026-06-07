from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from islo.custom.exec import ExecResult

from langchain_islo.sandbox import IsloSandbox, _map_http_status

TIMEOUT_EXIT_CODE = 124


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
    sb, _ = _make_sandbox()
    with patch("langchain_islo.sandbox.exec_and_wait_sync") as mock_exec:
        mock_exec.return_value = ExecResult(stdout="out", stderr="err", exit_code=0)
        result = sb.execute("echo hi")

    assert result.output == "outerr"
    assert result.exit_code == 0
    assert result.truncated is False

    # Command must be wrapped in a shell so pipes/redirects/here-docs work.
    args, _ = mock_exec.call_args
    assert args[0] is sb._client
    assert args[1] == "my-sandbox"
    assert args[2] == ["/bin/sh", "-c", "echo hi"]


def test_execute_stdout_only() -> None:
    sb, _ = _make_sandbox()
    with patch("langchain_islo.sandbox.exec_and_wait_sync") as mock_exec:
        mock_exec.return_value = ExecResult(stdout="hello", stderr="", exit_code=0)
        result = sb.execute("echo hello")
    assert result.output == "hello"


def test_execute_timeout_maps_to_124() -> None:
    sb, _ = _make_sandbox()
    with patch("langchain_islo.sandbox.exec_and_wait_sync") as mock_exec:
        mock_exec.return_value = ExecResult(
            stdout="", stderr="", exit_code=-1, timed_out=True
        )
        result = sb.execute("sleep 999", timeout=5)
    assert result.exit_code == TIMEOUT_EXIT_CODE
    assert "timed out" in result.output


def test_execute_timeout_zero_means_wait_forever() -> None:
    sb, _ = _make_sandbox()
    with patch("langchain_islo.sandbox.exec_and_wait_sync") as mock_exec:
        mock_exec.return_value = ExecResult(stdout="", stderr="", exit_code=0)
        sb.execute("echo hi", timeout=0)
    _, kwargs = mock_exec.call_args
    assert kwargs["timeout"] is None


def test_upload_rejects_relative_path() -> None:
    sb, _ = _make_sandbox()
    responses = sb.upload_files([("relative/path.txt", b"data")])
    assert len(responses) == 1
    assert responses[0].path == "relative/path.txt"
    assert responses[0].error == "invalid_path"


def test_upload_success_creates_parents_and_posts() -> None:
    sb, _ = _make_sandbox()
    http = MagicMock()
    http.__enter__.return_value = http
    response = MagicMock()
    response.raise_for_status.return_value = None
    http.post.return_value = response

    with (
        patch("langchain_islo.sandbox.httpx.Client", return_value=http),
        patch.object(sb, "execute") as mock_execute,
    ):
        responses = sb.upload_files([("/workspace/app.py", b"print('hi')")])

    assert responses[0].error is None
    # mkdir -p for the parent directory should have been issued.
    mkdir_cmd = mock_execute.call_args[0][0]
    assert mkdir_cmd.startswith("mkdir -p ")
    assert "/workspace" in mkdir_cmd
    # The POST hits the compute files endpoint with the path param.
    url = http.post.call_args[0][0]
    assert url == "https://ca.compute.islo.dev/sandboxes/my-sandbox/files"
    assert http.post.call_args[1]["params"] == {"path": "/workspace/app.py"}


def test_upload_partial_success() -> None:
    sb, _ = _make_sandbox()
    http = MagicMock()
    http.__enter__.return_value = http
    ok = MagicMock()
    ok.raise_for_status.return_value = None
    bad_response = MagicMock(status_code=403)
    err = httpx.HTTPStatusError("forbidden", request=MagicMock(), response=bad_response)
    bad = MagicMock()
    bad.raise_for_status.side_effect = err
    http.post.side_effect = [ok, bad]

    with (
        patch("langchain_islo.sandbox.httpx.Client", return_value=http),
        patch.object(sb, "execute"),
    ):
        responses = sb.upload_files([("/ok.txt", b"a"), ("/denied.txt", b"b")])

    assert responses[0].error is None
    assert responses[1].error == "permission_denied"


def test_download_success_returns_bytes() -> None:
    sb, _ = _make_sandbox()
    http = MagicMock()
    http.__enter__.return_value = http
    response = MagicMock(content=b"file-bytes")
    response.raise_for_status.return_value = None
    http.get.return_value = response

    with patch("langchain_islo.sandbox.httpx.Client", return_value=http):
        responses = sb.download_files(["/workspace/app.py"])

    assert responses[0].content == b"file-bytes"
    assert responses[0].error is None


def test_download_not_found() -> None:
    sb, _ = _make_sandbox()
    http = MagicMock()
    http.__enter__.return_value = http
    missing = MagicMock(status_code=404)
    err = httpx.HTTPStatusError("nope", request=MagicMock(), response=missing)
    response = MagicMock()
    response.raise_for_status.side_effect = err
    http.get.return_value = response

    with patch("langchain_islo.sandbox.httpx.Client", return_value=http):
        responses = sb.download_files(["/missing.txt"])

    assert responses[0].content is None
    assert responses[0].error == "file_not_found"


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
