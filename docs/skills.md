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
