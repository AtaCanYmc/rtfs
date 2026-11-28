/* Pyodide Web Worker for rtfs Live Web Playground */
/* global importScripts, loadPyodide */

let pyodideReady = null;

async function ensurePyodide() {
  if (pyodideReady) return pyodideReady;
  pyodideReady = (async () => {
    self.postMessage({ type: "status", message: "Loading Pyodide WebAssembly..." });
    importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.2/full/pyodide.js");
    const pyodide = await loadPyodide();
    self.postMessage({ type: "status", message: "Installing pydantic & pyrtfs (deps=False)..." });
    await pyodide.loadPackage("micropip");
    const micropip = pyodide.pyimport("micropip");
    await micropip.install("pydantic");
    await micropip.install("pyrtfs", { deps: false });
    self.postMessage({ type: "ready" });
    return pyodide;
  })();
  return pyodideReady;
}

self.onmessage = async (event) => {
  const { id, type, content, format, title } = event.data || {};
  if (type === "init") {
    try {
      await ensurePyodide();
    } catch (err) {
      self.postMessage({ id, ok: false, error: String(err) });
    }
    return;
  }

  if (type === "parse") {
    try {
      const pyodide = await ensurePyodide();
      pyodide.globals.set("_rtfs_content", content || "");
      pyodide.globals.set("_rtfs_format", format || "fountain");
      pyodide.globals.set("_rtfs_title", title || "Untitled");

      const resultJson = await pyodide.runPythonAsync(`
import json
from dataclasses import asdict
from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.parsers.fountain import FountainParser
from rtfs.parsers.fdx import FdxParser
from rtfs.parsers.transcript import TranscriptParser
from rtfs.exporters.json_exp import export_json
from rtfs.exporters.fountain_exp import export_fountain
from rtfs.exporters.fdx_exp import export_fdx
from rtfs.exporters.stats_exp import compute_stats, export_stats_mermaid

meta = ScriptMetadata(title=_rtfs_title, source="playground", url="playground://local")
fmt = _rtfs_format.lower().strip()
if fmt == "fdx":
    parser = FdxParser()
    ctype = "fdx"
elif fmt == "txt":
    parser = TranscriptParser()
    ctype = "text"
else:
    parser = FountainParser()
    ctype = "fountain"

doc = parser.parse(RawScript(content=_rtfs_content, content_type=ctype, metadata=meta))
stats = compute_stats(doc)
json.dumps({
    "astJson": export_json(doc),
    "fountain": export_fountain(doc),
    "fdx": export_fdx(doc),
    "stats": asdict(stats),
    "mermaid": export_stats_mermaid(stats),
}, ensure_ascii=False)
`);
      self.postMessage({ id, ok: true, result: JSON.parse(resultJson) });
    } catch (err) {
      self.postMessage({ id, ok: false, error: err && err.message ? err.message : String(err) });
    }
  }
};
