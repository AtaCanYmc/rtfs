from __future__ import annotations

import importlib
from typing import Any

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "Action": ("rtfs.core.models", "Action"),
    "BatchItemResult": ("rtfs.core.client", "BatchItemResult"),
    "CacheBackend": ("rtfs.core.cache", "CacheBackend"),
    "CacheInfo": ("rtfs.core.cache", "CacheInfo"),
    "Dialogue": ("rtfs.core.models", "Dialogue"),
    "DiskCacheBackend": ("rtfs.core.cache", "DiskCacheBackend"),
    "FdxParser": ("rtfs.parsers.fdx", "FdxParser"),
    "MemoryCacheBackend": ("rtfs.core.cache", "MemoryCacheBackend"),
    "NullCacheBackend": ("rtfs.core.cache", "NullCacheBackend"),
    "RTFSClient": ("rtfs.core.client", "RTFSClient"),
    "RawScript": ("rtfs.core.models", "RawScript"),
    "RedisCacheBackend": ("rtfs.core.cache", "RedisCacheBackend"),
    "Scene": ("rtfs.core.models", "Scene"),
    "ScriptAggregator": ("rtfs.core.aggregator", "ScriptAggregator"),
    "ScriptDocument": ("rtfs.core.models", "ScriptDocument"),
    "ScriptMetadata": ("rtfs.core.models", "ScriptMetadata"),
    "ScriptStats": ("rtfs.exporters.stats_exp", "ScriptStats"),
    "SearchResult": ("rtfs.core.models", "SearchResult"),
    "Transition": ("rtfs.core.models", "Transition"),
    "compute_stats": ("rtfs.exporters.stats_exp", "compute_stats"),
    "create_cache": ("rtfs.core.cache", "create_cache"),
    "export_fdx": ("rtfs.exporters.fdx_exp", "export_fdx"),
    "export_fountain": ("rtfs.exporters.fountain_exp", "export_fountain"),
    "export_json": ("rtfs.exporters.json_exp", "export_json"),
    "export_txt": ("rtfs.exporters.fountain_exp", "export_txt"),
    "filter_scenes": ("rtfs.core.aggregator", "filter_scenes"),
    "parse_file": ("rtfs.core.aggregator", "parse_file"),
    "parse_scene_range": ("rtfs.core.aggregator", "parse_scene_range"),
    "render_document": ("rtfs.core.client", "render_document"),
}

__all__ = sorted(_LAZY_IMPORTS)


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr)
    raise AttributeError(f"module 'rtfs' has no attribute {name!r}")
