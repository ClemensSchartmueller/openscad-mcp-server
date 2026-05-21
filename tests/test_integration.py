import os
import pytest
from config import config
import server

# Check if OpenSCAD is installed to decide if we run integration tests
openscad_installed = os.path.exists(config.openscad_path)

@pytest.mark.skipif(not openscad_installed, reason="OpenSCAD not installed")
def test_live_integration():
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
