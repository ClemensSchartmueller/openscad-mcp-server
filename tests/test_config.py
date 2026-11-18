from unittest.mock import patch

import config as config_module
from config import (
    Config,
    default_openscad_path,
    WINDOWS_DEFAULT_OPENSCAD_PATH,
    MACOS_APP_OPENSCAD_PATH,
)


def test_default_openscad_path_windows():
    with patch.object(config_module.sys, "platform", "win32"):
        assert default_openscad_path() == WINDOWS_DEFAULT_OPENSCAD_PATH


def test_default_openscad_path_linux_uses_path_lookup():
    with patch.object(config_module.sys, "platform", "linux"), \
         patch.object(config_module.shutil, "which", return_value="/usr/bin/openscad"):
        assert default_openscad_path() == "/usr/bin/openscad"


def test_default_openscad_path_linux_not_on_path():
    with patch.object(config_module.sys, "platform", "linux"), \
         patch.object(config_module.shutil, "which", return_value=None):
        assert default_openscad_path() == "openscad"


def test_default_openscad_path_macos_app_bundle_fallback():
    with patch.object(config_module.sys, "platform", "darwin"), \
         patch.object(config_module.shutil, "which", return_value=None), \
         patch.object(config_module.os.path, "exists", side_effect=lambda p: p == MACOS_APP_OPENSCAD_PATH):
        assert default_openscad_path() == MACOS_APP_OPENSCAD_PATH


def test_openscad_path_env_override(monkeypatch):
    monkeypatch.setenv("OPENSCAD_PATH", "/opt/openscad/bin/openscad")
    assert Config().openscad_path == "/opt/openscad/bin/openscad"


def test_empty_openscad_path_env_uses_default(monkeypatch):
    monkeypatch.setenv("OPENSCAD_PATH", "")
    with patch.object(config_module, "default_openscad_path", return_value="/usr/bin/openscad"):
        assert Config().openscad_path == "/usr/bin/openscad"
