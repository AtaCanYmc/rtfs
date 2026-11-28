# Use Cases & Best Practices

[Back to docs index](README.md)

## Use Cases

| Domain | Workflow | Recommended Entry Point |
| :--- | :--- | :--- |
| **LLM / AI Agents** | Bounded-context scene retrieval without loading a full 120-page script into context. | `rtfs mcp` (`get_scenes`, `rtfs://script/{source}/{slug}/scenes/{offset}/{limit}`) |
| **NLP & ML Datasets** | Streaming element-level records (`action`, `dialogue`, `transition`) into training/eval pipelines. | `rtfs parse --format jsonl` / `iter_jsonl()` |
| **Screenwriting & Script Doctoring** | Round-trip conversion between `.fountain`, `.fdx` (Final Draft), and `.json`, plus draft comparison. | `rtfs parse`, `rtfs diff` |
| **Character & Pacing Analysis** | Measuring dialogue/action ratios, INT/EXT splits, and speaking turns across merged character aliases. | `rtfs stats`, `compute_stats()` |
| **Self-Hosted Microservices** | Exposing screenplay search, parsing, and analytics over HTTP inside internal tools. | `rtfs serve` (`pyrtfs[api]`) |

## Best Practices & Recommendations

1. **Always Enable Caching in Production**: Use `disk://~/.cache/rtfs` for local CLI/SDK work or `redis://` for multi-worker services (`RTFS_CACHE_URL`) to avoid redundant network requests and respect archive rate limits.
2. **Bound Context for LLMs**: Prefer `get_scenes` with `start_scene`/`end_scene` or `--scene-range` + `--character` filtering instead of passing full-script JSON into prompts.
3. **Prefer `JSONL` for Large Corpora**: Use `iter_jsonl(doc)` or `--format jsonl` when ingesting multiple scripts; it streams one element per line without buffering a single monolithic JSON tree.
4. **Handle Scanned PDFs Explicitly**: Catch `ScannedPdfError` when parsing user-supplied PDFs and wire an `ocr_hook(pdf_bytes) -> str` if your pipeline processes image-only scans.
5. **Pin `rtfs schema` for Downstream Validation**: Export `rtfs schema > schema.json` in CI to validate downstream parsers or structured-output consumers against `ScriptDocument`.
