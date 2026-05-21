import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

class Config:
    def __init__(self):
        # Default OpenSCAD path on Windows
        self._openscad_path = os.environ.get(
            "OPENSCAD_PATH", 
            r"C:\Program Files\OpenSCAD\openscad.com"
        )
        
        # Default workspace directory in user's home directory
        default_workspace = os.path.join(os.path.expanduser("~"), "openscad-workspace")
        self._workspace_dir = os.environ.get("OPENSCAD_WORKSPACE", default_workspace)
        
        # Timeout for OpenSCAD processes
        try:
            self._render_timeout = int(os.environ.get("OPENSCAD_TIMEOUT", "120"))
        except ValueError:
            self._render_timeout = 120

    @property
    def openscad_path(self) -> str:
        return self._openscad_path

    @openscad_path.setter
    def openscad_path(self, value: str):
        self._openscad_path = value

    @property
    def workspace_dir(self) -> str:
        # Resolve and ensure the directory exists
        resolved = os.path.abspath(os.path.expanduser(self._workspace_dir))
        os.makedirs(resolved, exist_ok=True)
        return resolved

    @workspace_dir.setter
    def workspace_dir(self, value: str):
        self._workspace_dir = value

    @property
    def render_timeout(self) -> int:
        return self._render_timeout

    @render_timeout.setter
    def render_timeout(self, value: int):
        self._render_timeout = value

    def get_openscad_path(self, override: str | None = None) -> str:
        """Get the OpenSCAD executable path, prioritizing an override if provided."""
        return override if override else self.openscad_path

    def get_workspace_dir(self, override: str | None = None) -> str:
        """Get the workspace directory, prioritizing an override if provided, and ensure it exists."""
        target_dir = override if override else self.workspace_dir
        resolved = os.path.abspath(os.path.expanduser(target_dir))
        os.makedirs(resolved, exist_ok=True)
        return resolved

# Global configuration instance
config = Config()
