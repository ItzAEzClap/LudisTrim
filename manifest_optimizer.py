from manifest_manager import YAML_PATH, JSON_PATH
from enum import IntFlag
import json
import time
import yaml

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader
import yaml

class TAGS(IntFlag):
    SAVE = 1 << 0
    CONFIG = 1 << 1
    WINDOWS = 1 << 2
    LINUX = 1 << 3
    MAC = 1 << 4

    ANY_OS = WINDOWS | LINUX | MAC

def optimize_manifest():
    raw_yaml = get_raw_yaml()
    processed_manifest = {}

    total_games = 0
    valid_games = 0
    for game_name, game_data in raw_yaml.items():
        total_games += 1

        entry = {}

        if files := extract_files(game_data, game_name):
            entry["files"] = files
        
        if registry := extract_registry(game_data):
            entry["registry"] = registry
    
        if not entry:
            continue

        install_dir = extract_install_dir(game_data)

        if install_dir and install_dir != game_name:
            entry["installDir"] = install_dir

        if ids := extract_game_ids(game_data):
            entry["ids"] = ids

        valid_games += 1
        processed_manifest[game_name] = entry

    print(f"Processed {total_games} number of games")
    print(f"Found {valid_games} number of valid games")

    try:
        with open(JSON_PATH, "w", encoding="utf-8") as tf:
            #json.dump(processed_manifest, tf, separators=(',', ':'))
            json.dump(processed_manifest, tf, indent=2)
    except OSError as e:
        print(f"Failed to save optimized code to {JSON_PATH}: {e}")

    print_size_reduction()


def extract_files(game_data, name):
    parsed_files = {}

    for file_path, file_info in game_data.get("files", {}).items():
        fixed_path = abstract_file_path(sanitize_file_path(file_path))
        path_lower = fixed_path.lower()

        if not file_info:
            parsed_files[fixed_path] = TAGS.ANY_OS
            continue

        flags = TAGS(0)

        file_tags = file_info.get("tags", [])
        if "save" in file_tags: flags |= TAGS.SAVE
        if "config" in file_tags: flags |= TAGS.CONFIG

        
        if path_lower.startswith(("<base>", "<root>")):
            flags |= TAGS.ANY_OS

        elif path_lower.startswith("<home>"):
            if path_lower.startswith(("<home>/saved games", "<home>/games/", "<home>/my games/")):
                flags |= TAGS.WINDOWS
            elif path_lower.startswith(("<home>/library", "<home>/application support/")):
                flags |= TAGS.MAC
            elif path_lower.startswith(("<home>/.", "<home>/config.unity3d/")):
                flags |= TAGS.LINUX
            else:
                flags |= TAGS.ANY_OS

        elif path_lower.startswith("<win"):
            flags |= TAGS.WINDOWS

        elif path_lower.startswith(("<xdgdata>", "<xdgconfig>")):
            flags |= TAGS.LINUX | TAGS.MAC

        if not (flags & TAGS.ANY_OS):
            flags |= TAGS.ANY_OS
        
        parsed_files[fixed_path] = flags

    return parsed_files

def sanitize_file_path(raw_path):
    normalized_slashes = raw_path.replace("\\", "/").replace("//", "/")
    
    env_rules = {
        "$user": "<home>",
        "$home": "<home>",
        "$xdg_data_home": "<xdgData>",
        "$xdg_config_home": "<xdgConfig>",
        "<home>/deck/": "<home>/",
        }

    return replace_case_insensitive(normalized_slashes, env_rules)

def abstract_file_path(clean_path):
    macro_rules = {
        "/data/library/application support": "/<xdgData>",
        "/data/library/preferences": "/<xdgConfig>",
        "<home>/library/application support": "<xdgData>",
        "<home>/library/preferences": "<xdgConfig>",

        "<home>/.steam/steam": "<root>",

        "<home>/appdata/locallow": "<winLocalAppDataLow>",
        "<home>/appdata/local": "<winLocalAppData>",
        "<home>/appdata/roaming": "<winAppData>",
        "<home>/documents": "<winDocuments>",

        "<home>/.local/share": "<xdgData>",
        "<home>/.config": "<xdgConfig>"
    }

    return replace_case_insensitive(clean_path, macro_rules)

def replace_case_insensitive(file_path, rule_map):
    for search_key, replacement in rule_map.items():
        while True:
            lower_path = file_path.lower()
            idx = lower_path.find(search_key)

            if idx == -1:
                break

            start = idx
            end = idx + len(search_key)
            file_path = file_path[:start] + replacement + file_path[end:]
    
    return file_path


def extract_install_dir(game_data):
    if install := game_data.get("installDir"):
        return next(iter(install.keys()))
    return None

def extract_registry(game_data):
    parsed_registry = {}

    for reg_path, reg_info in game_data.get("registry", {}).items():
        if reg_info:
            parsed_registry[reg_path] = 0
            continue

        flags = 0
        reg_tags = reg_info.get("tags", [])
        if "save" in reg_tags: flags |= TAGS.SAVE
        if "config" in reg_tags: flags |= TAGS.CONFIG

        parsed_registry[reg_path] = flags

    return parsed_registry

def extract_game_ids(game_data):
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

def get_raw_yaml():
    if not YAML_PATH.exists():
        raise FileNotFoundError(f"Cannot build cache: Source manifest file missing at '{YAML_PATH}'.")

    start = time.perf_counter()
    try:
        with open(YAML_PATH, "r", encoding="utf-8") as yf:
            raw_yaml = yaml.load(yf, Loader=SafeLoader)
    except (yaml.YAMLError, OSError) as e:
        raise ValueError(f"Failed to parse source manifest YAML: {e}")
    end = time.perf_counter()

    print(f"Loading the manifest.yaml file took {(end - start):.2f} seconds")
    return raw_yaml

def print_size_reduction():
    if not YAML_PATH.exists() or not JSON_PATH.exists():
        return
    
    yaml_size = YAML_PATH.stat().st_size / 1024
    json_size = JSON_PATH.stat().st_size / 1024
    reduction = ((yaml_size - json_size) / yaml_size) * 100

    print("Size Reduction Summary:")
    print(f"  Original YAML:  {yaml_size:.2f} KB")
    print(f"  Optimized JSON: {json_size:.2f} KB")
    print(f"  Shrunk by:      {reduction:.1f}%")