import os
import uuid
import json
import logging
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP, Image

from config import config
import openscad_runner as runner
import scad_parser as parser

# Configure logging to write to stderr so it doesn't interfere with stdio transport
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("openscad-mcp-server")

# Initialize FastMCP server
mcp = FastMCP("openscad")

def resolve_secure_path(filepath: str, workspace_dir: str) -> str:
    """Resolve filepath relative to workspace_dir and ensure it is inside it to prevent directory traversal."""
    workspace_abs = os.path.abspath(workspace_dir)
    
    if os.path.isabs(filepath):
        filepath_abs = os.path.abspath(filepath)
    else:
        filepath_abs = os.path.abspath(os.path.join(workspace_abs, filepath))
        
    # Standardize separator trailing to avoid substring matches
    workspace_prefix = workspace_abs if workspace_abs.endswith(os.sep) else workspace_abs + os.sep
    
    if not filepath_abs.startswith(workspace_prefix) and filepath_abs != workspace_abs:
        raise ValueError(
            f"Access denied: Path '{filepath}' is outside the authorized workspace directory."
        )
    return filepath_abs


def get_temp_filepath(workspace_dir: str, extension: str) -> str:
    """Generate a temporary filename in the workspace directory that matches .gitignore rules."""
    filename = f"temp_{uuid.uuid4().hex}.{extension.lstrip('.')}"
    return os.path.join(workspace_dir, filename)


@mcp.tool()
def configure_server(
    openscad_path: Optional[str] = None,
    workspace_dir: Optional[str] = None,
    render_timeout: Optional[int] = None
) -> str:
    """Get or update server configuration (OpenSCAD path, workspace directory, timeout) at runtime.
    
    If no arguments are provided, it returns the current configuration.
    """
    if openscad_path is not None:
        config.openscad_path = openscad_path
    if workspace_dir is not None:
        config.workspace_dir = workspace_dir
    if render_timeout is not None:
        config.render_timeout = render_timeout
        
    return (
        f"Server configuration:\n"
        f"- OpenSCAD executable: {config.openscad_path}\n"
        f"- Workspace directory: {config.workspace_dir}\n"
        f"- Render timeout: {config.render_timeout} seconds"
    )


@mcp.tool()
def create_scad(
    filename: str,
    code: str,
    overwrite: bool = False,
    workspace_dir: Optional[str] = None
) -> str:
    """Create a new .scad file in the workspace with the given OpenSCAD code.
    
    Args:
        filename: Name of the file (e.g. 'cube.scad'). If no extension, .scad is added.
        code: The OpenSCAD source code.
        overwrite: Whether to overwrite the file if it already exists.
        workspace_dir: Optional workspace directory override.
    """
    effective_workspace = config.get_workspace_dir(workspace_dir)
    if not filename.endswith(".scad"):
        filename += ".scad"
        
    try:
        target_path = resolve_secure_path(filename, effective_workspace)
    except ValueError as e:
        return str(e)
        
    if os.path.exists(target_path) and not overwrite:
        return f"Error: File '{filename}' already exists. Set overwrite=True to replace it."
        
    try:
        # Ensure parent directories exist within the workspace
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(code)
        rel_path = os.path.relpath(target_path, effective_workspace)
        return f"Successfully created '{rel_path}'."
    except Exception as e:
        return f"Failed to write file: {e}"


@mcp.tool()
def edit_scad(
    filepath: str,
    code: str,
    workspace_dir: Optional[str] = None
) -> str:
    """Overwrite or update the contents of an existing .scad file.
    
    Args:
        filepath: Path to the .scad file (relative to workspace or absolute).
        code: The new OpenSCAD source code.
        workspace_dir: Optional workspace directory override.
    """
    effective_workspace = config.get_workspace_dir(workspace_dir)
    try:
        target_path = resolve_secure_path(filepath, effective_workspace)
    except ValueError as e:
        return str(e)
        
    if not os.path.exists(target_path):
        return f"Error: File '{filepath}' does not exist. Use create_scad to create new files."
        
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(code)
        rel_path = os.path.relpath(target_path, effective_workspace)
        return f"Successfully updated '{rel_path}'."
    except Exception as e:
        return f"Failed to write file: {e}"


@mcp.tool()
def list_models(
    pattern: Optional[str] = None,
    workspace_dir: Optional[str] = None
) -> str:
    """List all .scad files in the workspace with details (size, last modified).
    
    Args:
        pattern: Optional glob pattern or substring to filter files (e.g. '*gear*' or 'box').
        workspace_dir: Optional workspace directory override.
    """
    effective_workspace = config.get_workspace_dir(workspace_dir)
    import fnmatch
    
    scad_files = []
    for root, _, files in os.walk(effective_workspace):
        for file in files:
            if file.endswith(".scad"):
                abs_path = os.path.join(root, file)
                try:
                    rel_path = os.path.relpath(abs_path, effective_workspace)
                except ValueError:
                    # Occurs on Windows if paths are on different drives
                    rel_path = abs_path
                
                # Apply pattern filtering if provided
                if pattern:
                    if not fnmatch.fnmatch(rel_path.lower(), pattern.lower()) and pattern.lower() not in rel_path.lower():
                        continue
                        
                try:
                    stats = os.stat(abs_path)
                    scad_files.append({
                        "filepath": rel_path,
                        "size_bytes": stats.st_size,
                        "modified": stats.st_mtime
                    })
                except Exception:
                    pass
                   
    if not scad_files:
        msg = f"No .scad files found in workspace '{effective_workspace}'"
        if pattern:
            msg += f" matching pattern '{pattern}'."
        else:
            msg += "."
        return msg
           
    # Format as markdown table
    import datetime
    lines = ["| Filepath | Size (Bytes) | Last Modified |", "| --- | --- | --- |"]
    for f in sorted(scad_files, key=lambda x: x["filepath"]):
        mtime = datetime.datetime.fromtimestamp(f["modified"]).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"| {f['filepath']} | {f['size_bytes']} | {mtime} |")
        
    return f"Models in workspace: {effective_workspace}\n\n" + "\n".join(lines)


@mcp.tool()
def get_parameters(
    filepath: str,
    workspace_dir: Optional[str] = None
) -> str:
    """Extract Customizer parameters, modules, and functions from a .scad file.
    
    Args:
        filepath: Path to the .scad file.
        workspace_dir: Optional workspace directory override.
    """
    effective_workspace = config.get_workspace_dir(workspace_dir)
    try:
        target_path = resolve_secure_path(filepath, effective_workspace)
    except ValueError as e:
        return str(e)
        
    if not os.path.exists(target_path):
        return f"Error: File '{filepath}' does not exist."
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        parsed = parser.parse_scad(content)
        return json.dumps(parsed, indent=2)
    except Exception as e:
        return f"Error parsing file '{filepath}': {e}"


@mcp.tool()
def validate_scad(
    filepath: Optional[str] = None,
    code: Optional[str] = None,
    openscad_path: Optional[str] = None,
    workspace_dir: Optional[str] = None
) -> str:
    """Check OpenSCAD code or file for syntax errors without rendering.
    
    Specify either `filepath` or raw `code`.
    """
    effective_openscad = config.get_openscad_path(openscad_path)
    effective_workspace = config.get_workspace_dir(workspace_dir)
    
    temp_file_created = False
    target_path = None
    
    if filepath:
        try:
            target_path = resolve_secure_path(filepath, effective_workspace)
        except ValueError as e:
            return str(e)
        if not os.path.exists(target_path):
            return f"Error: File '{filepath}' does not exist."
    elif code:
        # Write code to a temporary file
        target_path = get_temp_filepath(effective_workspace, ".scad")
        temp_file_created = True
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            return f"Error creating validation temp file: {e}"
    else:
        return "Error: Either 'filepath' or 'code' must be provided."
        
    # Run in validation mode: output to stdout (-) with format csg to verify code syntax
    cmd = runner.build_command(
        openscad_path=effective_openscad,
        filepath=target_path,
        output_path="-"
    )
    cmd.extend(["--export-format", "csg"])
    
    result = runner.run_openscad(cmd, timeout=config.render_timeout, output_path="-")
    
    # Clean up temp file
    if temp_file_created and target_path and os.path.exists(target_path):
        try:
            os.remove(target_path)
        except Exception as e:
            logger.warning(f"Failed to delete temp file '{target_path}': {e}")
            
    if result.success:
        if result.errors:
            warnings = "\n".join(result.errors)
            return f"Validation passed with warnings:\n{warnings}"
        return "Validation passed! No errors or warnings found."
    else:
        errors_str = "\n".join(result.errors) if result.errors else result.stderr
        return f"Validation failed:\n{errors_str}"


@mcp.tool()
def render_preview(
    filepath: str,
    width: int = 800,
    height: int = 600,
    camera: Optional[str] = None,
    colorscheme: str = "Cornfield",
    variables: Optional[Dict[str, Any]] = None,
    openscad_path: Optional[str] = None,
    workspace_dir: Optional[str] = None
) -> List[Any]:
    """Render an OpenSCAD file to a PNG preview image and return it.
    
    Use this to visually verify your design.
    
    Args:
        filepath: Path to the .scad file.
        width: Width of the preview image (default 800).
        height: Height of the preview image (default 600).
        camera: Camera settings. Format: 'transx,transy,transz,rotx,roty,rotz,distance' or 'eyex,eyey,eyez,centerx,centery,centerz'.
        colorscheme: Colorscheme (e.g. 'Cornfield', 'Sunset', 'Metallic', 'Classic').
        variables: Dict of variables to override.
        openscad_path: Optional override for the OpenSCAD executable path.
        workspace_dir: Optional override for the workspace directory.
    """
    effective_openscad = config.get_openscad_path(openscad_path)
    effective_workspace = config.get_workspace_dir(workspace_dir)
    
    try:
        target_path = resolve_secure_path(filepath, effective_workspace)
    except ValueError as e:
        return [str(e)]
        
    if not os.path.exists(target_path):
        return [f"Error: File '{filepath}' does not exist."]
        
    # Output to a temporary PNG inside the workspace
    output_png = get_temp_filepath(effective_workspace, ".png")
    
    cmd = runner.build_command(
        openscad_path=effective_openscad,
        filepath=target_path,
        output_path=output_png,
        variables=variables,
        imgsize=f"{width},{height}",
        camera=camera,
        colorscheme=colorscheme,
        viewall=True,
        autocenter=True
    )
    
    result = runner.run_openscad(cmd, timeout=config.render_timeout, output_path=output_png)
    
    if result.success and os.path.exists(output_png):
        try:
            with open(output_png, "rb") as f:
                img_bytes = f.read()
            # Clean up the file immediately
            os.remove(output_png)
            
            # Return text status and image content block
            return [
                f"Successfully rendered preview of '{filepath}' ({width}x{height})",
                Image(data=img_bytes, format="png")
            ]
        except Exception as e:
            if os.path.exists(output_png):
                try:
                    os.remove(output_png)
                except:
                    pass
            return [f"Error reading generated preview image: {e}"]
    else:
        # Clean up temp file on failure if it exists
        if os.path.exists(output_png):
            try:
                os.remove(output_png)
            except:
                pass
        errors_str = "\n".join(result.errors) if result.errors else result.stderr
        return [f"Render failed:\n{errors_str}"]


@mcp.tool()
def render_stl(
    filepath: str,
    output_path: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
    openscad_path: Optional[str] = None,
    workspace_dir: Optional[str] = None
) -> str:
    """Render a .scad file to an STL 3D model.
    
    Args:
        filepath: Path to the .scad file.
        output_path: Optional output path (relative to workspace or absolute). Defaults to same name as scad with .stl.
        variables: Dict of variables to override.
        openscad_path: Optional override for the OpenSCAD executable path.
        workspace_dir: Optional override for the workspace directory.
    """
    effective_openscad = config.get_openscad_path(openscad_path)
    effective_workspace = config.get_workspace_dir(workspace_dir)
    
    try:
        target_scad = resolve_secure_path(filepath, effective_workspace)
    except ValueError as e:
        return str(e)
        
    if not os.path.exists(target_scad):
        return f"Error: File '{filepath}' does not exist."
        
    if not output_path:
        # Replace extension with .stl
        base, _ = os.path.splitext(target_scad)
        target_stl = base + ".stl"
    else:
        try:
            target_stl = resolve_secure_path(output_path, effective_workspace)
        except ValueError as e:
            return str(e)
            
    # Ensure directory exists for output
    os.makedirs(os.path.dirname(target_stl), exist_ok=True)
    
    cmd = runner.build_command(
        openscad_path=effective_openscad,
        filepath=target_scad,
        output_path=target_stl,
        variables=variables
    )
    
    result = runner.run_openscad(cmd, timeout=config.render_timeout, output_path=target_stl)
    
    if result.success:
        rel_stl = os.path.relpath(target_stl, effective_workspace)
        return f"Successfully rendered STL to '{rel_stl}'."
    else:
        errors_str = "\n".join(result.errors) if result.errors else result.stderr
        return f"Render failed:\n{errors_str}"


@mcp.tool()
def export_model(
    filepath: str,
    format: str,
    output_path: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
    openscad_path: Optional[str] = None,
    workspace_dir: Optional[str] = None
) -> str:
    """Export an OpenSCAD model to a specific format (stl, 3mf, amf, off, dxf, svg, png).
    
    Args:
        filepath: Path to the .scad file.
        format: Output format (stl, 3mf, amf, off, dxf, svg, png).
        output_path: Optional output path.
        variables: Dict of variables to override.
        openscad_path: Optional override for the OpenSCAD executable path.
        workspace_dir: Optional override for the workspace directory.
    """
    effective_openscad = config.get_openscad_path(openscad_path)
    effective_workspace = config.get_workspace_dir(workspace_dir)
    
    fmt = format.lower().lstrip(".")
    supported_formats = {"stl", "3mf", "amf", "off", "dxf", "svg", "png"}
    if fmt not in supported_formats:
        return f"Error: Unsupported format '{format}'. Supported formats: {', '.join(supported_formats)}"
        
    try:
        target_scad = resolve_secure_path(filepath, effective_workspace)
    except ValueError as e:
        return str(e)
        
    if not os.path.exists(target_scad):
        return f"Error: File '{filepath}' does not exist."
        
    if not output_path:
        base, _ = os.path.splitext(target_scad)
        target_out = f"{base}.{fmt}"
    else:
        # Standardize extension
        if not output_path.lower().endswith(f".{fmt}"):
            output_path = f"{output_path}.{fmt}"
        try:
            target_out = resolve_secure_path(output_path, effective_workspace)
        except ValueError as e:
            return str(e)
            
    os.makedirs(os.path.dirname(target_out), exist_ok=True)
    
    if fmt == "png":
        cmd = runner.build_command(
            openscad_path=effective_openscad,
            filepath=target_scad,
            output_path=target_out,
            variables=variables,
            imgsize="800,600",
            viewall=True,
            autocenter=True
        )
    else:
        cmd = runner.build_command(
            openscad_path=effective_openscad,
            filepath=target_scad,
            output_path=target_out,
            variables=variables
        )
        
    result = runner.run_openscad(cmd, timeout=config.render_timeout, output_path=target_out)
    
    if result.success:
        rel_out = os.path.relpath(target_out, effective_workspace)
        return f"Successfully exported model to '{rel_out}' in {fmt.upper()} format."
    else:
        errors_str = "\n".join(result.errors) if result.errors else result.stderr
        return f"Export failed:\n{errors_str}"


@mcp.tool()
def batch_export(
    filepath: str,
    parameter_sets: List[Dict[str, Any]],
    format: str = "stl",
    openscad_path: Optional[str] = None,
    workspace_dir: Optional[str] = None
) -> str:
    """Export a model multiple times with different parameter sets.
    
    Args:
        filepath: Path to the .scad file.
        parameter_sets: List of dictionaries, each specifying variable overrides.
        format: Output format (default 'stl').
        openscad_path: Optional override for the OpenSCAD executable path.
        workspace_dir: Optional override for the workspace directory.
    """
    effective_openscad = config.get_openscad_path(openscad_path)
    effective_workspace = config.get_workspace_dir(workspace_dir)
    
    fmt = format.lower().lstrip(".")
    supported_formats = {"stl", "3mf", "amf", "off", "dxf", "svg", "png"}
    if fmt not in supported_formats:
        return f"Error: Unsupported format '{format}'."
        
    try:
        target_scad = resolve_secure_path(filepath, effective_workspace)
    except ValueError as e:
        return str(e)
        
    if not os.path.exists(target_scad):
        return f"Error: File '{filepath}' does not exist."
        
    base_name, _ = os.path.splitext(os.path.basename(target_scad))
    results = []
    
    for idx, variables in enumerate(parameter_sets):
        suffix_parts = []
        for k, v in list(variables.items())[:3]:
            # Simplify values for the filename suffix
            val_str = str(v).replace('[', '').replace(']', '').replace(',', '_').replace(' ', '').replace('"', '')
            suffix_parts.append(f"{k}_{val_str}")
        suffix = "_".join(suffix_parts) if suffix_parts else f"set{idx+1}"
        
        output_filename = f"{base_name}_{suffix}.{fmt}"
        output_dir = os.path.dirname(target_scad)
        target_out = os.path.join(output_dir, output_filename)
        
        if fmt == "png":
            cmd = runner.build_command(
                openscad_path=effective_openscad,
                filepath=target_scad,
                output_path=target_out,
                variables=variables,
                imgsize="800,600",
                viewall=True,
                autocenter=True
            )
        else:
            cmd = runner.build_command(
                openscad_path=effective_openscad,
                filepath=target_scad,
                output_path=target_out,
                variables=variables
            )
            
        result = runner.run_openscad(cmd, timeout=config.render_timeout, output_path=target_out)
        
        rel_out = os.path.relpath(target_out, effective_workspace)
        if result.success:
            results.append(f"Set {idx+1} ({variables}): Success -> '{rel_out}'")
        else:
            errors_str = "; ".join(result.errors) if result.errors else "Unknown compilation error"
            results.append(f"Set {idx+1} ({variables}): Failed -> {errors_str}")
            
    return "Batch export results:\n" + "\n".join(results)


if __name__ == "__main__":
    mcp.run()
