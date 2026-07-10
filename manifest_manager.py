import json
import logging
import urllib.request
import urllib.error
from enum import IntFlag
from typing import Dict, Any, Optional

import config

# Attempt to use the C-based YAML loader for massive speed gains
try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader
import yaml


# Extracted Magic Numbers
NETWORK_TIMEOUT = 10


class TAGS(IntFlag):
    SAVE = 1 << 0
    CONFIG = 1 << 1
    WINDOWS = 1 << 2
    LINUX = 1 << 3
    MAC = 1 << 4


def get_cached_etag() -> str:
    if config.ETAG_FILE_PATH.exists():
        try:
            with open(config.ETAG_FILE_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    return ""


def sync_manifest() -> bool:
    config.YAML_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    headers = {}
    if etag := get_cached_etag():
        headers["If-None-Match"] = etag

    # Fetch manifest
    try:
        req = urllib.request.Request(config.LUDUSAVI_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT) as res:
            content = res.read().decode("utf-8")
            response_headers = res.headers
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return True
        logging.error(f"Network verification failed: HTTP {e.code}")
        return False
    except Exception as e:
        logging.error(f"Update connection failed: {e}")
        return False

    tmp_yaml = config.YAML_FILE_PATH.with_suffix('.yaml.tmp')
    with open(tmp_yaml, "w", encoding="utf-8") as f:
        f.write(content)
    
    # pathlib atomic replace
    tmp_yaml.replace(config.YAML_FILE_PATH)

    if new_etag := response_headers.get("ETag"):
        with open(config.ETAG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(new_etag)

    return True


def load_manifest() -> Dict[str, Any]:
    if config.JSON_FILE_PATH.exists():
        try:
            with open(config.JSON_FILE_PATH, "r", encoding="utf-8") as jf:
                return json.load(jf)
        except (json.JSONDecodeError, OSError):
            logging.warning("Cached JSON manifest is corrupted. Attempting rebuild...")

    if not config.YAML_FILE_PATH.exists():
        logging.info("Local manifest missing. Attempting network synchronization...")

        if not sync_manifest():
            raise RuntimeError(
                "\n[!] Fatal Error: Could not download the game manifest.\n"
                "    An active internet connection is required for the initial setup."
            )

    logging.info("Building manifest cache...")
    build_cache()

    if not config.JSON_FILE_PATH.exists():
        raise RuntimeError("[!] Fatal Error: Failed to generate JSON manifest cache folder structure.")

    with open(config.JSON_FILE_PATH, "r", encoding="utf-8") as jf:
        return json.load(jf)

import time
import os



def build_cache() -> None:
    if not config.YAML_FILE_PATH.exists():
        raise FileNotFoundError(f"Cannot build cache: Source manifest file missing at '{config.YAML_FILE_PATH}'.")

    try:
        with open(config.YAML_FILE_PATH, "r", encoding="utf-8") as yf:
            raw_yaml = yaml.load(yf, Loader=SafeLoader)
    except (yaml.YAMLError, OSError) as e:
        raise ValueError(f"Failed to parse source manifest YAML: {e}")

    processed_manifest = {}

    i = 0
    for game_name, game_data in raw_yaml.items():
        i = i + 1
        entry = {}

        # Optimized loop: Only run extraction if the key explicitly exists
        if "files" in game_data:
            files = extract_files(game_data)
            if files:
                entry["files"] = files
                
        if "registry" in game_data:
            registry = extract_registry(game_data)
            if registry:
                entry["registry"] = registry

        if not entry:
            continue

        if ids := extract_game_ids(game_data):
            entry["id"] = ids

        install_dir = extract_install_dir(game_data)
        
        # Omit installDir from JSON if it matches the game name to save space
        if install_dir and install_dir != game_name:
            entry["installDir"] = install_dir

        processed_manifest[game_name] = entry

    logging.info(f"Processed {i} number of games")
    with open(config.JSON_FILE_PATH, "w", encoding="utf-8") as tf:
        #json.dump(processed_manifest, tf, separators=(',', ':'))
        json.dump(processed_manifest, tf, indent=2)


def extract_registry(game_data: Dict[str, Any]) -> Dict[str, int]:
    parsed_registry = {}

    for reg_path, reg_info in game_data.get("registry", {}).items():
        if not reg_info:
            parsed_registry[reg_path] = 0
            continue

        flags = 0
        reg_tags = reg_info.get("tags", [])
        if "save" in reg_tags: flags |= TAGS.SAVE
        if "config" in reg_tags: flags |= TAGS.CONFIG

        parsed_registry[reg_path] = flags

    return parsed_registry

def extract_files(game_data: Dict[str, Any]) -> Dict[str, int]:
    parsed_files = {}
    os_bit_mapping = {
        "windows": TAGS.WINDOWS,
        "linux": TAGS.LINUX,
        "mac": TAGS.MAC,
        "darwin": TAGS.MAC
    }

    for file_path, file_info in game_data.get("files", {}).items():
        if not file_info:
            # Fallback to current OS bit representation if file info mapping is empty
            parsed_files[file_path] = os_bit_mapping.get(config.CURRENT_OS, 0)
            continue

        flags = 0
        file_tags = file_info.get("tags", [])
        if "save" in file_tags: flags |= TAGS.SAVE
        if "config" in file_tags: flags |= TAGS.CONFIG

        # Determine OS
        normalized_path = normalize_path_placeholders(file_path)
        path_lower = normalized_path.lower()

        if path_lower.startswith(("<base>", "<game>", "<root>")):
            flags |= (TAGS.WINDOWS | TAGS.LINUX | TAGS.MAC)

        #if path_lower.startswith("<base>", "<game>", "<root>"):
        #    flags |= (TAGS.WINDOWS | TAGS.LINUX | TAGS.MAC)

        
        if "<win" in path_lower or "<home>/saved games" in path_lower:
            flags |= TAGS.WINDOWS

        if "application support" in path_lower or path_lower.startswith("<home>/library/"):
            flags |= TAGS.MAC
        
        if "<xdg" in path_lower or "<home>/." in path_lower:
            flags |= (TAGS.LINUX | TAGS.MAC)

        if path_lower.startswith("<home>/"):
            flags |= (TAGS.WINDOWS | TAGS.LINUX | TAGS.MAC)





        if not (flags & (TAGS.WINDOWS | TAGS.LINUX | TAGS.MAC)):
            continue


        
        parsed_files[normalized_path] = flags

    return parsed_files

def normalize_path_placeholders(file_path: str) -> str:
    if file_path.startswith("~"):
        file_path = os.path.expanduser(file_path).replace("\\", "/")

    path_lower = file_path.lower()

    if path_lower.startswith("$home/"):
        file_path = "<home>/" + file_path[6:]
        path_lower = file_path.lower()

    if path_lower.startswith("$xdg_config_home/"):
        return "<xdgConfig>/" + file_path[17:]
    elif path_lower.startswith("$xdg_data_home/"):
        return "<xdgData>/" + file_path[15:]

    if "appdata/locallow" in path_lower:
        idx = path_lower.find("appdata/locallow")
        return "<winLocalAppDataLow>" + file_path[idx + 16:]
        
    elif "appdata/local" in path_lower:
        idx = path_lower.find("appdata/local")
        return "<winLocalAppData>" + file_path[idx + 13:]
        
    elif "appdata/roaming" in path_lower:
        idx = path_lower.find("appdata/roaming")
        return "<winAppData>" + file_path[idx + 15:]
        
    elif "<home>/documents" in path_lower:
        return file_path.replace(file_path[path_lower.find("<home>/documents"):path_lower.find("<home>/documents") + 16], "<winDocuments>")
    
    elif "c:/programdata" in path_lower:
        replaced = file_path.replace(file_path[path_lower.find("c:/programdata"):path_lower.find("c:/programdata") + 14], "<winProgramData>")
        return replaced
    
    return file_path

def extract_install_dir(game_data: Dict[str, Any]) -> Optional[str]:
    if install := game_data.get("installDir"):
        return next(iter(install.keys()))
    return None


def extract_game_ids(game_data: Dict[str, Any]) -> Dict[str, Any]:
    ids = {}
    id_block = game_data.get("id", {})

    for launcher in ("steam", "gog"):
        launcher_ids = []

        if launcher_id := game_data.get(launcher, {}).get("id"):
            launcher_ids.append(str(launcher_id))

        # Optimized list comprehension for faster `.extend()` performance
        launcher_ids.extend([str(i) for i in id_block.get(f"{launcher}Extra", [])])

        if launcher_ids:
            ids[launcher] = launcher_ids
    
    if lutris := id_block.get("lutris"):
        ids["lutris"] = str(lutris)

    return ids