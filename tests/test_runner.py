import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from openscad_runner import to_scad_value, build_command, parse_stderr_errors, run_openscad

def test_to_scad_value():
    assert to_scad_value(True) == "true"
    assert to_scad_value(False) == "false"
    assert to_scad_value(42) == "42"
    assert to_scad_value(3.14) == "3.14"
    assert to_scad_value("hello") == '"hello"'
    assert to_scad_value('"already_quoted"') == '"already_quoted"'
    assert to_scad_value('he"llo') == '"he\\"llo"'
    assert to_scad_value([1, True, "val"]) == '[1, true, "val"]'
    assert to_scad_value((1.5, 2)) == '[1.5, 2]'
    
    with pytest.raises(ValueError):
        to_scad_value(None)
    with pytest.raises(ValueError):
        to_scad_value({"a": 1})


def test_build_command():
    cmd = build_command(
        openscad_path="openscad.com",
        filepath="model.scad",
        output_path="out.stl",
        variables={"size": 10, "name": "box", "show": True},
        imgsize="800,600",
        camera="0,0,0",
        colorscheme="Sunset",
        projection="ortho",
        viewall=True,
        autocenter=True
    )
    
    # Check that all options are formatted into the command list
    assert cmd[0] == "openscad.com"
    assert "-o" in cmd
    assert cmd[cmd.index("-o") + 1] == "out.stl"
    
    # Check variables
    assert "-D" in cmd
    # Verify exact -D arguments are there
    assert "size=10" in cmd
    assert 'name="box"' in cmd
    assert "show=true" in cmd
    
    # Check other flags
    assert "--imgsize=800,600" in cmd
    assert "--camera=0,0,0" in cmd
    assert "--colorscheme=Sunset" in cmd
    assert "--projection=ortho" in cmd
    assert "--viewall" in cmd
    assert "--autocenter" in cmd
    
    # Check that input file is at the end
    assert cmd[-1] == "model.scad"


def test_parse_stderr_errors():
    stderr_sample = (
        "Compiling design...\n"
        "ERROR: Syntax error in line 15\n"
        "ECHO: \"Volume: 120\"\n"
        "WARNING: Can't open library 'utils.scad'\n"
    )
    errors = parse_stderr_errors(stderr_sample)
    assert len(errors) == 2
    assert "ERROR: Syntax error in line 15" in errors
    assert "WARNING: Can't open library 'utils.scad'" in errors


@patch("subprocess.run")
def test_run_openscad_success(mock_run):
    # Setup mock process response
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "Rendering complete"
    mock_process.stderr = "Compiling design...\nECHO: \"Volume: 10\""
    mock_run.return_value = mock_process
    
    cmd = [r"C:\Program Files\OpenSCAD\openscad.com", "model.scad"]
    result = run_openscad(cmd)
    
    assert result.success is True
    assert result.returncode == 0
    assert result.stdout == "Rendering complete"
    assert len(result.errors) == 0


@patch("subprocess.run")
def test_run_openscad_null_device(mock_run):
    # Setup mock process response
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "Rendering complete"
    mock_process.stderr = "Compiling design...\n"
    mock_run.return_value = mock_process
    
    cmd = [r"C:\Program Files\OpenSCAD\openscad.com", "model.scad"]
    result = run_openscad(cmd, output_path="NUL")
    
    assert result.success is True
    assert result.returncode == 0
    assert len(result.errors) == 0


@patch("subprocess.run")
def test_run_openscad_compilation_error(mock_run):
    mock_process = MagicMock()
    mock_process.returncode = 0  # Sometimes exit code is 0 on compilation error
    mock_process.stdout = ""
    mock_process.stderr = "Compiling design...\nERROR: Syntax error in line 4\nParsing design failed!"
    mock_run.return_value = mock_process
    
    cmd = [r"C:\Program Files\OpenSCAD\openscad.com", "model.scad"]
    result = run_openscad(cmd)
    
    assert result.success is False
    assert len(result.errors) >= 1
    assert "ERROR: Syntax error in line 4" in result.errors


@patch("subprocess.run")
def test_run_openscad_timeout(mock_run):
    cmd = [r"C:\Program Files\OpenSCAD\openscad.com", "model.scad"]
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=cmd, timeout=10, output="out", stderr=None)
    
    result = run_openscad(cmd, timeout=10)
    
    assert result.success is False
    assert result.returncode == -2
    assert "timed out" in result.stderr


@patch("subprocess.run")
@patch("os.environ.copy")
def test_run_openscad_library_paths(mock_env_copy, mock_run):
    mock_env = {"PATH": "/usr/bin"}
    mock_env_copy.return_value = mock_env
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_run.return_value = mock_process
    
    cmd = [r"C:\Program Files\OpenSCAD\openscad.com", "model.scad"]
    run_openscad(cmd, library_paths=["/my/lib1", "/my/lib2"])
    
    # Assert env is set correctly
    called_env = mock_run.call_args[1]["env"]
    assert "OPENSCADPATH" in called_env
    assert os.path.abspath("/my/lib1") in called_env["OPENSCADPATH"]
    assert os.path.abspath("/my/lib2") in called_env["OPENSCADPATH"]
