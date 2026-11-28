# AI Agent Skill & MCP Setup

[Back to docs index](README.md)

Install the `rtfs` skill for AI coding agents or connect the FastMCP server to your editor.

## Install the Agent Skill

### Via `skills` CLI (`npx`)

```bash
npx skills add AtaCanYmc/rtfs
```

### Manual / Symlink (Claude Code, Cursor, Antigravity)

```bash
git clone https://github.com/AtaCanYmc/rtfs.git ~/.local/share/rtfs
mkdir -p ~/.gemini/config/skills ~/.claude/skills
ln -s ~/.local/share/rtfs/skills/rtfs ~/.gemini/config/skills/rtfs
ln -s ~/.local/share/rtfs/skills/rtfs ~/.claude/skills/rtfs
```

## Install the `rtfs` CLI & MCP Server

```bash
# uv (recommended)
uv tool install "pyrtfs[mcp]"

# pipx
pipx install "pyrtfs[mcp]"

# pip
pip install "pyrtfs[mcp]"

# Homebrew
brew install AtaCanYmc/tap/rtfs
```

## MCP Client Configuration (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "rtfs": {
      "command": "rtfs",
      "args": ["mcp", "--transport", "stdio"],
      "env": {
        "RTFS_CACHE_URL": "disk://~/.cache/rtfs"
      }
    }
  }
}
```

## Optional Extras Matrix

| Extra | Install | Enables |
| :--- | :--- | :--- |
| `mcp` | `pip install "pyrtfs[mcp]"` | `rtfs mcp` FastMCP server (`stdio` / `sse`) |
| `redis` | `pip install "pyrtfs[redis]"` | `redis://` and `rediss://` async cache backends |
| `api` | `pip install "pyrtfs[api]"` | `rtfs serve` FastAPI HTTP server |
| `ocr` | `pip install "pyrtfs[ocr]"` | `rtfs parse --ocr` local Tesseract OCR |
| `semantic` | `pip install "pyrtfs[semantic]"` | `search_scenes_semantic` (`fastembed`) |
| `tui` | `pip install "pyrtfs[tui]"` | `rtfs view` interactive Textual reader |
| `all` | `pip install "pyrtfs[all]"` | All optional extras above |
