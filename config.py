import os
import sys
import getpass
import json
import logging
from pathlib import Path
from typing import Dict, Any

# Set up basic logging for the application
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Static OS Detection
CURRENT_OS = {"win32": "windows", "linux": "linux", "darwin": "mac"}.get(sys.platform, sys.platform)
IS_WINDOWS = CURRENT_OS == "windows"
IS_LINUX = CURRENT_OS == "linux"
IS_MAC = CURRENT_OS == "mac"
IS_UNIX = IS_LINUX or IS_MAC

# Static URLs and Base Directories
LUDUSAVI_URL = "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/master/data/manifest.yaml"

BASE_DIR = Path("resources")
YAML_FILE_PATH = BASE_DIR / "manifest.yaml"
JSON_FILE_PATH = BASE_DIR / "manifest.json"
ETAG_FILE_PATH = BASE_DIR / "manifest.etag"
CONFIG_FILE_PATH = BASE_DIR / "config.json"

PATH_MAPPING: Dict[str, str] = {}


def get_path_mapping() -> Dict[str, str]:
    """Lazy-loads the OS path mapping only when accessed."""
    global PATH_MAPPING
    if PATH_MAPPING:
        return PATH_MAPPING

    home = Path.home()

    mapping = {
        "<home>": str(home),
        "<osUserName>": getpass.getuser(),
        "<storeUserId>": "*"
    }

    if IS_WINDOWS:
        mapping.update({
            "<winAppData>": os.environ.get("APPDATA", ""),
            "<winLocalAppData>": os.environ.get("LOCALAPPDATA", ""),
            "<winLocalAppDataLow>": str(home / "AppData" / "LocalLow"),
            "<winDocuments>": str(home / "Documents"),
            "<winProgramData>": os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
            "<winDir>": os.environ.get("WINDIR", "C:\\Windows"),
            "<winPublic>": os.environ.get("PUBLIC", "C:\\Users\\Public")
        })
    elif IS_LINUX:
        mapping.update({
            "<xdgConfig>": os.environ.get("XDG_CONFIG_HOME", str(home / ".config")),
            "<xdgData>": os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share")),
        })

    # Sort by length descending for safest string replacements
    sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
    PATH_MAPPING = {k: mapping[k] for k in sorted_keys}
    print(PATH_MAPPING)
    return PATH_MAPPING


def load_user_config() -> Dict[str, Any]:
    CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE_PATH.exists():
        logging.info("Loading configuration file...")
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as cf:
                return json.load(cf)
        except (json.JSONDecodeError, TypeError, PermissionError, OSError) as e:
            logging.error(f"Loading failed ({type(e).__name__}). Resetting to defaults.")

    logging.info("Creating new configuration...")
    return create_user_config()


def create_user_config() -> Dict[str, Any]:
    mapping = get_path_mapping()
    user_config = {
        "settings": {
            "backup_destination": str(Path(mapping["<home>"]) / "Backups"),
            "compress_backups": False
        }
    }

    try:
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(user_config, f, indent=4)
    except OSError as e:
        logging.error(f"Failed to save configuration file to disk: {e}")
    
    return user_config