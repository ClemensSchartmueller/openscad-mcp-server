# OpenSCAD Model Context Protocol (MCP) Server

A local Model Context Protocol (MCP) server written in Python using FastMCP. This server enables LLM assistants (such as Gemini, Claude, and VS Code Copilot) to interact directly with a local installation of OpenSCAD to write, inspect, edit, validate, and render parametric 3D models.

```
                  ┌──────────────────────┐
                  │      AI Assistant    │
                  └──────────┬───────────┘
                             │ stdio JSON-RPC
                             ▼
  ┌──────────────────────────────────────────────────────┐
  │              OpenSCAD MCP Server (Python)            │
  │  ┌───────────────┐ ┌───────────────┐ ┌────────────┐  │
  │  │   server.py   │ │runner_scad.py │ │ parser.py  │  │
  │  └───────┬───────┘ └───────┬───────┘ └─────┬──────┘  │
  └──────────┼─────────────────┼───────────────┼─────────┘
             │                 │               │
             ▼                 ▼               │
   ┌───────────────────┐  ┌──────────────┐     │
   │  Workspace Files  │  │ openscad.com │     │ Reads Customizer
   │  (.scad / .stl)   │  │   (Subproc)  │◄────┘ Parameters
   └───────────────────┘  └──────────────┘
```

## Features

1. **Parametric Modeling Control**: Write and edit `.scad` model code directly from LLM contexts.
2. **Visual Feedback (Previews)**: Renders 3D models into PNG images and feeds them back directly into the AI assistant so it can "see" what it designed.
3. **Customizer Support**: Parses `.scad` files to extract parameters, sections, sliders, and dropdown options defined by the user.
4. **Validation**: Check for syntax errors without full renders.
5. **Batch Export**: Export models in multiple formats and configurations in a single run.
6. **Path Traversal Security**: Automatically locks operations to an authorized workspace directory to protect the local filesystem.

---

## Prerequisites

- **Python 3.10+**
- **OpenSCAD (2021.01 or newer)**
  - *Windows*: Ensure OpenSCAD is installed (typically at `C:\Program Files\OpenSCAD\openscad.com`).
  - *macOS/Linux*: Ensure `openscad` is installed and on your system `PATH`.

---

## Installation

1. Navigate to the project folder:
   ```powershell
   cd c:\dev\openscad-mcp-server
   ```
2. Set up a virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate  # On macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

---

## Configuration

The server supports configuration via environment variables. You can copy the template `.env.example` to `.env` to customize settings:

```env
# OpenSCAD binary path (will default to typical locations if omitted)
OPENSCAD_PATH=C:\Program Files\OpenSCAD\openscad.com

# Working directory for reading/writing CAD models
OPENSCAD_WORKSPACE=C:\Users\your-username\openscad-workspace

# Render process timeout in seconds
OPENSCAD_TIMEOUT=120
```

### Dynamic Runtime Overrides
Crucially, the server also allows clients to query or update settings at runtime using the `configure_server` tool, and all file/render tools accept an optional `workspace_dir` or `openscad_path` parameter to override settings on-the-fly.

---

## Integrating with AI Clients

### Claude Desktop
Add the following to your `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "openscad": {
      "command": "C:\\dev\\openscad-mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\dev\\openscad-mcp-server\\server.py"],
      "env": {
        "OPENSCAD_WORKSPACE": "C:\\Users\\your-username\\openscad-workspace"
      }
    }
  }
}
```

### Antigravity 2.0 / Cascade
Add the following block inside the `"mcpServers"` object in your `~/.gemini/config/mcp_config.json`:

```json
    "openscad": {
      "$typeName": "exa.cascade_plugins_pb.CascadePluginCommandTemplate",
      "command": "c:\\dev\\openscad-mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["c:\\dev\\openscad-mcp-server\\server.py"],
      "env": {
        "OPENSCAD_PATH": "C:\\Program Files\\OpenSCAD\\openscad.com"
      }
    }
```

### Gemini CLI / Settings
Add to your Gemini settings configuration block:

```json
{
  "mcpServers": {
    "openscad": {
      "command": "python",
      "args": ["c:\\dev\\openscad-mcp-server\\server.py"],
      "env": {
        "OPENSCAD_PATH": "C:\\Program Files\\OpenSCAD\\openscad.com"
      }
    }
  }
}
```

---

## Tool Reference

The OpenSCAD MCP server exposes the following tools:

| Tool Name | Parameters | Description |
|---|---|---|
| `configure_server` | `openscad_path?`, `workspace_dir?`, `render_timeout?` | Gets or sets current path and workspace settings. |
| `create_scad` | `filename`, `code`, `overwrite?`, `workspace_dir?` | Creates a new `.scad` file. Extension added automatically if omitted. |
| `edit_scad` | `filepath`, `code`, `workspace_dir?` | Overwrites code in an existing `.scad` file. |
| `list_models` | `pattern?`, `workspace_dir?` | Lists all `.scad` files in the workspace (with size and date metadata). |
| `get_parameters`| `filepath`, `workspace_dir?` | Parses customizer variables, modules, and functions. |
| `validate_scad` | `filepath?`, `code?`, `openscad_path?`, `workspace_dir?` | Runs OpenSCAD parser check to detect syntax errors. |
| `render_preview`| `filepath`, `width?`, `height?`, `camera?`, `colorscheme?`, `variables?` | Generates a PNG rendering of the model and returns it to the LLM. |
| `render_stl` | `filepath`, `output_path?`, `variables?` | Renders a `.scad` file to STL format. |
| `export_model`  | `filepath`, `format`, `output_path?`, `variables?` | Exports to `stl`, `3mf`, `amf`, `off`, `dxf`, `svg`, or `png`. |
| `batch_export`  | `filepath`, `parameter_sets`, `format?` | Exports multiple files based on varying parameter dictionaries. |

---

## Running Tests

Verify everything works by executing our test suite:

```powershell
.venv\Scripts\python -m pytest tests/ -v
```

---

## Interactive Debugging

You can test the tools interactively using the MCP Inspector tool:

```powershell
npx @modelcontextprotocol/inspector .venv\Scripts\python server.py
```
This launches a web console where you can call all tools and inspect their outputs (including image renders).

---

## Troubleshooting

- **Error: OpenSCAD executable not found**:
  Ensure that you specify `OPENSCAD_PATH` in your `.env` or client configuration pointing to `openscad.com` (on Windows, use `openscad.com` rather than `openscad.exe` as it redirects console output properly).
- **Access Denied**:
  The server validates that all files are inside the `workspace_dir`. If you attempt to access an absolute path outside this workspace, it will raise a security exception. Ensure your files are within the configured workspace.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.



