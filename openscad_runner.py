import os
import shutil
import subprocess
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class OpenSCADRunnerResult:
    """Result of running an OpenSCAD command."""
    def __init__(
        self,
        success: bool,
        returncode: int,
        stdout: str,
        stderr: str,
        errors: List[str],
        output_path: Optional[str] = None
    ):
        self.success = success
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.errors = errors
        self.output_path = output_path

    def __repr__(self) -> str:
        return (
            f"OpenSCADRunnerResult(success={self.success}, returncode={self.returncode}, "
            f"errors={self.errors}, output_path={self.output_path})"
        )


def to_scad_value(val: Any) -> str:
    """Convert a Python value into an OpenSCAD-compatible literal string."""
    if val is None:
        raise ValueError("None (null) values are not supported in OpenSCAD.")
    if isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, str):
        # If the string is already quoted, don't double quote it
        if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
            return val
        # Escape double quotes inside the string
        escaped = val.replace('"', '\\"')
        return f'"{escaped}"'
    elif isinstance(val, (list, tuple)):
        items = [to_scad_value(item) for item in val]
        return f"[{', '.join(items)}]"
    elif isinstance(val, dict):
        raise ValueError("Dictionaries (objects) are not supported as OpenSCAD variables.")
    else:
        # Fallback to string representation
        return str(val)


def build_command(
    openscad_path: str,
    filepath: str,
    output_path: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
    imgsize: Optional[str] = None,
    camera: Optional[str] = None,
    colorscheme: Optional[str] = None,
    projection: Optional[str] = None,
    viewall: bool = False,
    autocenter: bool = False
) -> List[str]:
    """Construct the command line list for running OpenSCAD.
    
    Args:
        openscad_path: Path to the OpenSCAD executable (e.g. openscad.com).
        filepath: Path to the input .scad file.
        output_path: Path to the output file (STL, PNG, etc.).
        variables: Dictionary of variables to override via -D.
        imgsize: Image dimensions for PNG preview ("width,height").
        camera: Camera settings flag.
        colorscheme: Colorscheme flag (e.g. "Cornfield", "Metallic").
        projection: Projection flag ("ortho" or "perspective").
        viewall: Translate camera to fit the whole model in view.
        autocenter: Align camera to target center of the model.
    """
    cmd = [openscad_path]

    # Output file
    if output_path:
        cmd.extend(["-o", output_path])

    # Variable overrides (-D flag)
    if variables:
        for name, value in variables.items():
            scad_val = to_scad_value(value)
            cmd.extend(["-D", f"{name}={scad_val}"])

    # Preview/rendering options
    if imgsize:
        cmd.append(f"--imgsize={imgsize}")
    if camera:
        cmd.append(f"--camera={camera}")
    if colorscheme:
        cmd.append(f"--colorscheme={colorscheme}")
    if projection:
        cmd.append(f"--projection={projection}")
    if viewall:
        cmd.append("--viewall")
    if autocenter:
        cmd.append("--autocenter")

    # Input file
    cmd.append(filepath)
    return cmd


def parse_stderr_errors(stderr: str) -> List[str]:
    """Parse stderr output from OpenSCAD to extract warning and error messages.
    
    OpenSCAD outputs compilation errors and warnings to stderr.
    We look for 'ERROR:' or 'Error:' or compilation failures.
    """
    errors = []
    for line in stderr.splitlines():
        line_stripped = line.strip()
        # Standard OpenSCAD error patterns
        if (
            line_stripped.startswith("ERROR:") 
            or "Error:" in line_stripped 
            or "Parsing design failed" in line_stripped
            or "WARNING:" in line_stripped  # Include warnings since they often cause silent failures
        ):
            errors.append(line_stripped)
    return errors


def _to_text(value: Any) -> str:
    """Normalize captured process output to str.

    subprocess.TimeoutExpired always carries bytes (or None), even with text=True.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_openscad(
    cmd: List[str],
    timeout: int = 120,
    output_path: Optional[str] = None,
    library_paths: Optional[List[str]] = None
) -> OpenSCADRunnerResult:
    """Execute OpenSCAD as a subprocess and handle its output.
    
    Args:
        cmd: List of command arguments.
        timeout: Execution timeout in seconds.
        output_path: The expected output file path, if any, to verify existence.
        library_paths: List of additional directories to search for libraries.
    """
    # Verify the executable exists
    openscad_bin = cmd[0]
    # Accept an existing file path or a command name resolvable on PATH.
    # A missing absolute path is reported here too instead of surfacing later
    # as a generic FileNotFoundError from subprocess.
    if not os.path.exists(openscad_bin) and not shutil.which(openscad_bin):
        return OpenSCADRunnerResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=f"OpenSCAD executable not found: {openscad_bin}",
            errors=[f"OpenSCAD executable not found: {openscad_bin}"]
        )

    # Set up environment variables (like OPENSCADPATH)
    env = os.environ.copy()
    if library_paths:
        # Join using path separator (semicolon on Windows, colon on Unix)
        sep = ";" if os.name == "nt" else ":"
        existing_path = env.get("OPENSCADPATH", "")
        additional_path = sep.join(os.path.abspath(p) for p in library_paths)
        if existing_path:
            env["OPENSCADPATH"] = f"{existing_path}{sep}{additional_path}"
        else:
            env["OPENSCADPATH"] = additional_path

    try:
        # Run the process
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env
        )
        
        stdout_str = process.stdout
        stderr_str = process.stderr
        returncode = process.returncode
        
        errors = parse_stderr_errors(stderr_str)
        
        # OpenSCAD exit codes are not always reliable for compilation errors.
        # We determine success based on:
        # 1. No exit errors (returncode == 0)
        # 2. No fatal 'ERROR:' in stderr
        # 3. If output_path is specified, the file must exist and be non-empty.
        has_fatal_error = any("ERROR:" in err or "Parsing design failed" in err for err in errors)
        
        success = (returncode == 0) and not has_fatal_error
        
        if output_path and success:
            is_null_device = output_path.upper() == "NUL" or output_path.lower() in ("/dev/null", "-")
            if not is_null_device:
                if not os.path.exists(output_path):
                    success = False
                    errors.append(f"Output file was not generated: {output_path}")
                elif os.path.getsize(output_path) == 0:
                    success = False
                    errors.append(f"Generated output file is empty: {output_path}")

        return OpenSCADRunnerResult(
            success=success,
            returncode=returncode,
            stdout=stdout_str,
            stderr=stderr_str,
            errors=errors,
            output_path=output_path if success else None
        )
        
    except subprocess.TimeoutExpired as e:
        logger.error(f"OpenSCAD process timed out after {timeout}s: {' '.join(cmd)}")
        return OpenSCADRunnerResult(
            success=False,
            returncode=-2,
            stdout=_to_text(e.stdout),
            stderr=_to_text(e.stderr) or f"Process timed out after {timeout} seconds.",
            errors=[f"Execution timed out after {timeout} seconds."]
        )
    except Exception as e:
        logger.exception("Failed to run OpenSCAD process")
        return OpenSCADRunnerResult(
            success=False,
            returncode=-3,
            stdout="",
            stderr=str(e),
            errors=[f"Internal error running OpenSCAD: {e}"]
        )
