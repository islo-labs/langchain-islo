"""Standard-suite integration tests against a live Islo sandbox.

Validates `IsloSandbox` with the deepagents `SandboxIntegrationTests` standard
suite (the contributing-guide requirement). Requires a live account:

    export ISLO_API_KEY="ak_..."
    make integration_test

The suite drives the inherited filesystem tools, which run `python3` and GNU
`grep` inside the sandbox, so the image must provide them. Islo's default
`islo-runner` image does NOT ship `python3`; use a python image (default
below) or one with `python3` installed.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import pytest
from islo import Islo
from langchain_tests.integration_tests import SandboxIntegrationTests

from langchain_islo import IsloSandbox

if TYPE_CHECKING:
    from collections.abc import Iterator

    from deepagents.backends.protocol import SandboxBackendProtocol

# Image must include python3 + GNU grep (see module docstring).
_IMAGE = os.environ.get("ISLO_TEST_IMAGE", "docker.io/library/python:3.12-slim")
_READY_STATES = {"running", "ready", "active"}

pytestmark = pytest.mark.skipif(
    not os.environ.get("ISLO_API_KEY"),
    reason="ISLO_API_KEY not set; skipping live Islo integration tests",
)


class TestIsloSandboxStandard(SandboxIntegrationTests):
    @pytest.fixture(scope="class")
    def sandbox(self) -> Iterator[SandboxBackendProtocol]:
        client = Islo()
        sb = client.sandboxes.create_sandbox(image=_IMAGE)
        for _ in range(90):
            status = str(client.sandboxes.get_sandbox(sb.name).status).lower()
            if status in _READY_STATES:
                break
            time.sleep(2)
        backend = IsloSandbox(client=client, sandbox=sb, poll_interval=1.0, timeout=120)
        try:
            yield backend
        finally:
            client.sandboxes.delete_sandbox(sb.name)
