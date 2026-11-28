from __future__ import annotations

import builtins
from unittest.mock import patch

import pytest

from rtfs.api.server import create_app


def test_create_app_raises_helpful_importerror_when_fastapi_missing() -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "fastapi":
            raise ImportError("No module named 'fastapi'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="pyrtfs\\[api\\]"):
            create_app()
