"""Lifecycle provider for Islo sandboxes.

[`IsloProvider`][langchain_islo.provider.IsloProvider] is an optional
convenience that creates, attaches to, and deletes Islo sandboxes and returns a
ready-to-use [`IsloSandbox`][langchain_islo.sandbox.IsloSandbox]. It is
duck-typed to the lifecycle shape deepagents expects of a sandbox provider
(``get_or_create`` / ``delete``) without importing the CLI package, mirroring the
``RunloopProvider`` pattern.
"""

from __future__ import annotations

from typing import Any

from islo import Islo

from langchain_islo.sandbox import IsloSandbox

_DEFAULT_IMAGE = "ubuntu:24.04"


class IsloProvider:
    """Create, attach to, and delete Islo sandboxes.

    Example:
        ```python
        from langchain_islo import IsloProvider

        provider = IsloProvider(api_key="ak_...")
        backend = provider.get_or_create(image="ubuntu:24.04")
        try:
            print(backend.execute("uname -a").output)
        finally:
            provider.delete(sandbox_id=backend.id)
        ```
    """

    def __init__(
        self,
        *,
        client: Islo | None = None,
        api_key: str | None = None,
        image: str = _DEFAULT_IMAGE,
    ) -> None:
        """Initialize the provider.

        Args:
            client: A pre-configured ``islo.Islo`` client. If omitted, one is
                created (reading ``ISLO_API_KEY`` / ``ISLO_BASE_URL`` from the
                environment, or ``api_key`` when provided).
            api_key: API key used to construct a client when ``client`` is not
                supplied.
            image: Default container image used when creating new sandboxes.
        """
        if client is None:
            client = Islo(api_key=api_key) if api_key else Islo()
        self._client = client
        self._default_image = image

    def get_or_create(
        self,
        *,
        sandbox_id: str | None = None,
        **kwargs: Any,
    ) -> IsloSandbox:
        """Attach to an existing sandbox or create a new one.

        Args:
            sandbox_id: If provided, attach to the existing Islo sandbox with
                this id instead of creating a new one.
            kwargs: Forwarded to ``client.sandboxes.create_sandbox(...)`` when
                creating (e.g. ``image``, ``vcpus``, ``memory_mb``, ``env``,
                ``gateway_profile``, ``snapshot_name``).

        Returns:
            A ready-to-use ``IsloSandbox``.
        """
        if sandbox_id is not None:
            sandbox = self._client.sandboxes.get_sandbox_by_id(sandbox_id)
        else:
            kwargs.setdefault("image", self._default_image)
            sandbox = self._client.sandboxes.create_sandbox(**kwargs)
        return IsloSandbox(client=self._client, sandbox=sandbox)

    def delete(self, *, sandbox_id: str, **_kwargs: Any) -> None:
        """Delete an Islo sandbox by id.

        Islo's delete API is keyed by sandbox *name*, so the id is resolved to a
        name first.
        """
        sandbox = self._client.sandboxes.get_sandbox_by_id(sandbox_id)
        self._client.sandboxes.delete_sandbox(sandbox.name)
