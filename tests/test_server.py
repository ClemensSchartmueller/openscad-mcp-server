import os
import shutil
import tempfile
import json
import pytest
from unittest.mock import patch, MagicMock

from config import config
from server import (
    configure_server,
    create_scad,
    edit_scad,
    list_models,
    get_parameters,
    validate_scad,
    render_preview,
    render_stl,
    export_model,
    batch_export
)
from openscad_runner import OpenSCADRunnerResult

@pytest.fixture
def temp_workspace():
    """Fixture to create a temporary directory for workspace tests."""
    temp_dir = tempfile.mkdtemp()
    original_workspace = config.workspace_dir
    config.workspace_dir = temp_dir
    yield temp_dir
    # Clean up
    shutil.rmtree(temp_dir)
    config.workspace_dir = original_workspace


def test_configure_server():
    res = configure_server(openscad_path="dummy_path", render_timeout=60)
    assert "dummy_path" in res
    assert "60 seconds" in res
    assert config.openscad_path == "dummy_path"
    assert config.render_timeout == 60


def test_create_and_edit_scad(temp_workspace):
    # Test create new scad file
    res = create_scad(filename="test_box.scad", code="cube(10);")
    assert "Successfully created" in res
    
    file_path = os.path.join(temp_workspace, "test_box.scad")
    assert os.path.exists(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        assert f.read() == "cube(10);"

    # Test overwrite warning
    res_err = create_scad(filename="test_box.scad", code="cube(20);", overwrite=False)
    assert "already exists" in res_err
    
    # Test overwrite success
    res_ok = create_scad(filename="test_box.scad", code="cube(20);", overwrite=True)
    assert "Successfully created" in res_ok
    with open(file_path, "r", encoding="utf-8") as f:
        assert f.read() == "cube(20);"

    # Test edit scad
    res_edit = edit_scad(filepath="test_box.scad", code="cube(30);")
    assert "Successfully updated" in res_edit
    with open(file_path, "r", encoding="utf-8") as f:
        assert f.read() == "cube(30);"
        
    # Test edit non-existent file
    res_edit_err = edit_scad(filepath="non_existent.scad", code="cube(10);")
    assert "does not exist" in res_edit_err


def test_list_models(temp_workspace):
    # Create a couple of models
    create_scad(filename="model_a.scad", code="cube(5);")
    create_scad(filename="sub/model_b.scad", code="cylinder(10);")
    
    res = list_models()
    assert "model_a.scad" in res
    assert "sub/model_b.scad" in res or "sub\\model_b.scad" in res
    
    # Filter by pattern
    res_filtered = list_models(pattern="*_a*")
    assert "model_a.scad" in res_filtered
    assert "model_b" not in res_filtered


def test_get_parameters(temp_workspace):
    code = """
    // Height of sphere
    height = 10; // [5:20]
    
    module sphere_mod() {
        sphere(height);
    }
    """
    create_scad(filename="sph.scad", code=code)
    
    res_json = get_parameters(filepath="sph.scad")
    parsed = json.loads(res_json)
    
    assert "parameters" in parsed
    params = {p["name"]: p for p in parsed["parameters"]}
    assert "height" in params
    assert params["height"]["value"] == 10
    assert params["height"]["min"] == 5
    assert params["height"]["max"] == 20
    assert params["height"]["description"] == "Height of sphere"


@patch("openscad_runner.run_openscad")
def test_validate_scad(mock_run, temp_workspace):
    # Mock validation pass
    mock_run.return_value = OpenSCADRunnerResult(
        success=True, returncode=0, stdout="", stderr="", errors=[]
    )
    
    res = validate_scad(code="cube(10);")
    assert "Validation passed" in res

    # Mock validation failure
    mock_run.return_value = OpenSCADRunnerResult(
        success=False, returncode=1, stdout="", stderr="ERROR: Syntax error", errors=["ERROR: Syntax error"]
    )
    
    res_fail = validate_scad(code="cube(10)")
    assert "Validation failed" in res_fail
    assert "ERROR: Syntax error" in res_fail


@patch("openscad_runner.run_openscad")
def test_render_stl(mock_run, temp_workspace):
    # Setup test file
    create_scad(filename="test.scad", code="cube(10);")
    
    # Mock runner to output a fake STL file
    def fake_render(*args, **kwargs):
        out_path = kwargs.get("output_path") or args[0][args[0].index("-o") + 1]
        with open(out_path, "w") as f:
            f.write("fake stl content")
        return OpenSCADRunnerResult(success=True, returncode=0, stdout="", stderr="", errors=[], output_path=out_path)
    
    mock_run.side_effect = fake_render
    
    res = render_stl(filepath="test.scad", output_path="out.stl")
    assert "Successfully rendered" in res
    assert os.path.exists(os.path.join(temp_workspace, "out.stl"))


@patch("openscad_runner.run_openscad")
def test_render_preview(mock_run, temp_workspace):
    create_scad(filename="test.scad", code="cube(10);")
    
    # Mock runner to output a fake PNG
    def fake_render(*args, **kwargs):
        out_path = kwargs.get("output_path") or args[0][args[0].index("-o") + 1]
        with open(out_path, "wb") as f:
            f.write(b"fake png data")
        return OpenSCADRunnerResult(success=True, returncode=0, stdout="", stderr="", errors=[], output_path=out_path)
    
    mock_run.side_effect = fake_render
    
    res_list = render_preview(filepath="test.scad")
    assert len(res_list) == 2
    assert "Successfully rendered preview" in res_list[0]
    
    # Check that it returned an Image type with correct data
    img_obj = res_list[1]
    assert img_obj._format == "png"
    assert img_obj.data == b"fake png data"
    
    # Check that temp png file was cleaned up
    # Wait, our code deletes it, so let's verify no temp files are left in workspace
    temp_files = [f for f in os.listdir(temp_workspace) if f.startswith("temp_")]
    assert len(temp_files) == 0


@patch("openscad_runner.run_openscad")
def test_export_model(mock_run, temp_workspace):
    create_scad(filename="test.scad", code="cube(10);")
    
    def fake_render(*args, **kwargs):
        out_path = kwargs.get("output_path") or args[0][args[0].index("-o") + 1]
        with open(out_path, "w") as f:
            f.write("fake 3mf content")
        return OpenSCADRunnerResult(success=True, returncode=0, stdout="", stderr="", errors=[], output_path=out_path)
    
    mock_run.side_effect = fake_render
    
    res = export_model(filepath="test.scad", format="3mf", output_path="out.3mf")
    assert "Successfully exported" in res
    assert "3MF" in res
    assert os.path.exists(os.path.join(temp_workspace, "out.3mf"))


@patch("openscad_runner.run_openscad")
def test_batch_export(mock_run, temp_workspace):
    create_scad(filename="test.scad", code="cube(size);")
    
    def fake_render(*args, **kwargs):
        out_path = kwargs.get("output_path") or args[0][args[0].index("-o") + 1]
        with open(out_path, "w") as f:
            f.write("fake stl")
        return OpenSCADRunnerResult(success=True, returncode=0, stdout="", stderr="", errors=[], output_path=out_path)
        
    mock_run.side_effect = fake_render
    
    param_sets = [
        {"size": 10},
        {"size": 20}
    ]
    
    res = batch_export(filepath="test.scad", parameter_sets=param_sets, format="stl")
    assert "Batch export results" in res
    assert "Success" in res
    
    # Check that both files exist
    assert os.path.exists(os.path.join(temp_workspace, "test_size_10.stl"))
    assert os.path.exists(os.path.join(temp_workspace, "test_size_20.stl"))
