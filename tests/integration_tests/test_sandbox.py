from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from islo import Islo
from langchain_tests.integration_tests import SandboxIntegrationTests

from langchain_islo import IsloSandbox

if TYPE_CHECKING:
    from collections.abc import Iterator

    from deepagents.backends.protocol import SandboxBackendProtocol

# Requires a live Islo account: set ISLO_API_KEY before running these.
pytestmark = pytest.mark.skipif(
    not os.environ.get("ISLO_API_KEY"),
    reason="ISLO_API_KEY not set; skipping live Islo integration tests",
)


class TestIsloSandboxStandard(SandboxIntegrationTests):
    @pytest.fixture
    def sandbox(self) -> Iterator[SandboxBackendProtocol]:
        client = Islo()
        sandbox = client.sandboxes.create_sandbox(image="ubuntu:24.04")
        backend = IsloSandbox(client=client, sandbox=sandbox)
        try:
            yield backend
        finally:
            client.sandboxes.delete_sandbox(sandbox.name)
