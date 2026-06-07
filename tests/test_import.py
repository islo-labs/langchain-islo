from __future__ import annotations

import langchain_islo


def test_import_islo() -> None:
    assert langchain_islo is not None
    assert hasattr(langchain_islo, "IsloSandbox")
    assert hasattr(langchain_islo, "IsloProvider")
