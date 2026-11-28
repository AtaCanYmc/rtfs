from __future__ import annotations

from unittest.mock import MagicMock, patch

from rtfs.core.aggregator import ScriptAggregator
from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider


class _DummyPluginProvider(BaseProvider):
    name = "dummy_plugin"
    supports_transcript = False

    async def search(self, query: str) -> list[SearchResult]:
        return []

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        return RawScript(
            content="",
            content_type="text",
            metadata=ScriptMetadata(title=result.title, source=self.name, url=result.url),
        )


async def test_aggregator_loads_entrypoint_providers() -> None:
    ep = MagicMock(name="dummy_plugin")
    ep.name = "dummy_plugin"
    ep.load.return_value = _DummyPluginProvider
    with patch("rtfs.core.aggregator.entry_points", return_value=[ep]):
        agg = ScriptAggregator(cache="memory://")
        assert "dummy_plugin" in agg.providers
        assert isinstance(agg.providers["dummy_plugin"], _DummyPluginProvider)
        await agg.close()
