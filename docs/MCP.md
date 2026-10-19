# Glyfetti MCP server

**English** | [Polski](MCP.pl.md)

The local MCP server lets an assistant inspect presets and fonts, create or refine
styles, see rendered PNG previews, and export an atlas ZIP or whole-title PNG.
It uses the [official Python SDK v2](https://py.sdk.modelcontextprotocol.io/), pinned
to the compatible `>=2.3,<3` release range. MCP needs **Python 3.11+**. The regular
CLI and local browser editor continue to work on Python 3.10 without this extra.

## Install

From a repository checkout, activate a Python 3.11+ environment and run:

```bash
python -m pip install -e ".[mcp]"
```

For a packaged installation, install the local wheel with its MCP extra, or use
`python -m pip install "glyfetti[mcp]"` when that release is available from your
package index. Installing the regular package does not install the MCP SDK.

## Connect a client

Generate a configuration using the same Python that has Glyfetti and its MCP extra:

```bash
python -m glyfetti.cli mcp --output-dir ./glyfetti-output --print-config
```

Copy the resulting `glyfetti` server entry into your client's MCP settings. The
`mcpServers` wrapper is used by clients such as Claude Desktop and Cursor; other
clients may wrap the same command and arguments differently. The command uses
the current Python executable and an absolute export path, so no working-directory
setting is needed. A generic template is in [examples/mcp-config.json](../examples/mcp-config.json).

For a direct launch:

```bash
python -m glyfetti.cli mcp --output-dir ./glyfetti-output
```

The process waits silently for MCP messages on **stdio**. This is not an HTTP URL;
normally the client launches and closes the process. There is no API key, model
subscription or network renderer required by the server. Diagnostics use stderr;
stdout carries the protocol. Do not put shell banners before the launch command.

## Tools

| Tool | Purpose |
|---|---|
| `list_presets` | List the 12 bundled looks. |
| `get_preset` | Get a complete editable preset with an absolute bundled font path. |
| `list_fonts` | List six bundled font aliases, paths and variable-axis ranges. |
| `check_font` | Check native character coverage; builds may compose missing Polish letters. |
| `expand_style` | Validate simple/mixed/raw JSON and return full raw settings. |
| `preview_style` | Return an inline PNG plus metrics at draft quality, without creating export folders. |
| `export_style` | Save a full-quality atlas ZIP or transparent title PNG, plus raw style JSON. |
| `analyze_reference_image` | Extract gradient colors and estimated outline from a local PNG/JPEG (`image` path and `style` dictionary). |

Both rendering tools accept `mode: "atlas"` or `mode: "title"` and an optional
`text` string. Actual newlines create separate preview/title lines. Text replaces
the style's `preview`; preview characters are included in atlas exports. Custom
fonts can use absolute local paths; relative paths resolve against the server's
working directory. Bundled aliases work with compact styles from any directory.

Example tool arguments:

```json
{
  "style": {
    "name": "victory",
    "simple": { "palette": "gold", "shine": 0.7, "depth_3d": 0.6 }
  },
  "mode": "title",
  "text": "LEVEL COMPLETE!"
}
```

Use these first with `preview_style`, refine the returned/raw style, then call
`export_style`. The server runs the existing Glyfetti renderer; it does not interpret
natural language by itself. Your assistant selects the style parameters.

## Export files and resources

Each successful export creates a fresh folder under `--output-dir`, named by a
32-character export ID. Files from earlier exports are not replaced. A title export
contains `title.png` and `style.json`; an atlas export contains `atlas.zip` and
`style.json`. The atlas ZIP includes PNG, BMFont/Unity metrics, previews and its build
report. PNG titles remain transparent regardless of the preview background.

The tool returns each file's local path, byte count, MIME type and resource URI, plus
a report including skipped characters. MCP clients can read the same artifact bytes
through these resources:

- `glyfetti://styles/schema` — the complete simple/raw JSON Schema.
- `glyfetti://exports/{export_id}/style.json` — editable raw style JSON.
- `glyfetti://exports/{export_id}/title.png` — a saved title image.
- `glyfetti://exports/{export_id}/atlas.zip` — a saved atlas archive.

Only generated artifact names in the configured export root can be read through
these resource templates. Artifacts persist after a client disconnects. Delete
unneeded export folders yourself. Font patch caches use the same location as the
CLI; previews may populate that cache. Fonts are not copied into exports. Saved
styles retain local font paths, which must be updated on another computer.

## Verify

After installing the extra, run:

```bash
python -m pytest tests/test_mcp.py tests/test_mcp_optional.py -q
```

Tests use the SDK client both in memory and over a real stdio subprocess. They check
tool discovery, previews, exports, resource readback, errors and current/legacy
client negotiation. Base Python 3.10 jobs test the optional-runtime message and run
the regular suite without the SDK. Symlink checks run where the OS permits creating
symlinks. Protocol tests do not require a third-party assistant account.
