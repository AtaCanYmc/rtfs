from __future__ import annotations

from rtfs.core.diff import diff_documents
from rtfs.core.models import Action, Dialogue, Scene, ScriptDocument, Transition
from rtfs.parsers.base import normalize_character_name


def format_scene_markup(scene: Scene, highlight_character: str | None = None) -> str:
    """Format a Scene as Rich markup with optional character highlighting."""
    target = normalize_character_name(highlight_character) if highlight_character else None
    lines = [f"[bold underline]{scene.heading}[/bold underline]", ""]
    for el in scene.elements:
        if isinstance(el, Action):
            lines.append(el.text)
            lines.append("")
        elif isinstance(el, Transition):
            lines.append(f"[dim]{el.text}[/dim]")
            lines.append("")
        elif isinstance(el, Dialogue):
            norm = normalize_character_name(el.character)
            color = "bold yellow" if (target and target in norm) else "bold cyan"
            lines.append(f"[{color}]{el.character}[/{color}]")
            if el.parenthetical:
                lines.append(f"[italic]({el.parenthetical})[/italic]")
            lines.append(el.lines)
            lines.append("")
    return "\n".join(lines)


def launch_viewer(
    doc: ScriptDocument,
    *,
    diff_doc: ScriptDocument | None = None,
    highlight_character: str | None = None,
) -> None:
    """Launch the interactive Textual screenplay viewer (requires pyrtfs[tui])."""
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal
        from textual.widgets import Footer, Header, ListItem, ListView, Static
    except ImportError as exc:
        raise ImportError(
            "Terminal TUI requires optional dependencies. Install with: pip install 'pyrtfs[tui]'"
        ) from exc

    class ScriptViewerApp(App[None]):
        BINDINGS = [("q", "quit", "Quit")]
        CSS = """
        #scene-list { width: 32; border: solid $accent; }
        #scene-body { width: 1fr; padding: 1 2; overflow-y: auto; }
        #diff-body { width: 1fr; padding: 1 2; border-left: solid $accent; overflow-y: auto; }
        """

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal():
                items = [
                    ListItem(Static(f"{s.scene_number}. {s.heading[:26]}"))
                    for s in doc.scenes
                ]
                yield ListView(*items, id="scene-list")
                initial = (
                    format_scene_markup(doc.scenes[0], highlight_character)
                    if doc.scenes
                    else "No scenes."
                )
                yield Static(initial, id="scene-body")
                if diff_doc is not None:
                    diff_text = diff_documents(doc, diff_doc) or "No differences."
                    yield Static(diff_text, id="diff-body")
            yield Footer()

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            idx = event.list_view.index or 0
            if 0 <= idx < len(doc.scenes):
                body = self.query_one("#scene-body", Static)
                body.update(format_scene_markup(doc.scenes[idx], highlight_character))

    ScriptViewerApp().run()
