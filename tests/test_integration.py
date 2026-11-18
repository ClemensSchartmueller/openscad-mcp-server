import os
import shutil
import pytest
from config import config
import server

# Check if OpenSCAD is installed to decide if we run integration tests
openscad_installed = os.path.exists(config.openscad_path) or shutil.which(config.openscad_path) is not None

@pytest.mark.skipif(not openscad_installed, reason="OpenSCAD not installed")
def test_live_integration(tmp_path, monkeypatch):
    # Keep the live run out of the user's real workspace
    monkeypatch.setattr(config, "workspace_dir", str(tmp_path))

    # 1. Create a test scad file
    res_create = server.create_scad("smoke_test.scad", "cube(15);")
    assert "Successfully created" in res_create
    
    try:
        # 2. Validate SCAD
        res_validate = server.validate_scad(filepath="smoke_test.scad")
        assert "Validation passed" in res_validate
        
        # 3. Render STL
        res_stl = server.render_stl(filepath="smoke_test.scad")
        assert "Successfully rendered STL" in res_stl
        
        # 4. Render Preview
        res_preview = server.render_preview(filepath="smoke_test.scad")
        assert len(res_preview) == 2
        assert "Successfully rendered preview" in res_preview[0]
        
    finally:
        # 5. Clean up generated files in the workspace
        workspace = server.config.get_workspace_dir()
        for f in ["smoke_test.scad", "smoke_test.stl"]:
            file_path = os.path.join(workspace, f)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass


@pytest.mark.skipif(not openscad_installed, reason="OpenSCAD not installed")
def test_render_preview_through_mcp(tmp_path, monkeypatch):
    """Regression: render_preview must serialize through the MCP layer.

    Calling server.render_preview() directly bypasses FastMCP's result
    conversion; without structured_output=False, mcp 1.x fails with
    "Unable to serialize unknown type: ...Image".
    """
    import asyncio
    import base64

    monkeypatch.setattr(config, "workspace_dir", str(tmp_path))
    assert "Successfully created" in server.create_scad("mcp_preview.scad", "cube(10);")

    result = asyncio.run(
        server.mcp.call_tool("render_preview", {"filepath": "mcp_preview.scad", "width": 200, "height": 150})
    )
    # Depending on the tool's output mode, call_tool returns content blocks or (content, structured)
    content = result[0] if isinstance(result, tuple) else result

    text_blocks = [c for c in content if c.type == "text"]
    image_blocks = [c for c in content if c.type == "image"]
    assert any("Successfully rendered preview" in c.text for c in text_blocks)
    assert len(image_blocks) == 1
    assert image_blocks[0].mimeType == "image/png"
    png = base64.b64decode(image_blocks[0].data)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
