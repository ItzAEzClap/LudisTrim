from manifest_manager import YAML_PATH, JSON_PATH
from enum import IntFlag
import json
import time
import re

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader
import yaml

def _compile_rules(rule_dict):
    sorted_keys = sorted(rule_dict.keys(), key=len, reverse=True)
    return {re.compile(re.escape(k), re.IGNORECASE): rule_dict[k] for k in sorted_keys}

ENV_RULES = _compile_rules({
    # Literal misspellings
    "$user": "<home>",
    "$home": "<home>",
    "$xdg_data_home": "<xdgData>",
    "$xdg_config_home": "<xdgConfig>",

    # Wrong format
    "<home>/application support": "<home>/library/application support",
    "<home>/preferences": "<home>/library/preferences",
    "<home>/.steam/steam": "<root>",
    "<home>/deck/": "<home>/",
})

MACRO_RULES = _compile_rules({
    "<home>/library/application support": "<macAppSupport>",
    "<home>/library/preferences": "<macPreferences>",

    "<home>/appdata/locallow": "<winLocalAppDataLow>",
    "<home>/appdata/local": "<winLocalAppData>",
    "<home>/appdata/roaming": "<winAppData>",
    "<home>/documents": "<winDocuments>",

    "<home>/.local/share": "<xdgData>",
    "<home>/.config": "<xdgConfig>"
})


class TAGS(IntFlag):
    SAVE = 1 << 0
    CONFIG = 1 << 1
    WINDOWS = 1 << 2
    LINUX = 1 << 3
    MAC = 1 << 4

    ANY_OS = WINDOWS | LINUX | MAC



def extract_files(game_data):
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
            elif path_lower.startswith(("<home>/.", "<home>/config.unity3d/")):
                flags |= TAGS.LINUX
            else:
                flags |= TAGS.ANY_OS

        elif path_lower.startswith("<win"):
            flags |= TAGS.WINDOWS

        elif path_lower.startswith(("<xdgdata>", "<xdgconfig>")):
            flags |= TAGS.LINUX

        elif path_lower.startswith("<mac"):
            flags |= TAGS.MAC

        if not (flags & TAGS.ANY_OS):
            flags |= TAGS.ANY_OS

        parsed_files[fixed_path] = flags

    return parsed_files


def extract_registry(game_data):
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


def extract_install_dir(game_data):
    if install := game_data.get("installDir"):
        return next(iter(install.keys()))
    return None


def extract_game_ids(game_data):
    ids = {}
    id_block = game_data.get("id", {})

    for launcher in ("steam", "gog"):
        launcher_ids = []

        if launcher_id := game_data.get(launcher, {}).get("id"):
            try:
                launcher_ids.append(int(launcher_id))
            except (ValueError, TypeError):
                pass

        for i in id_block.get(f"{launcher}Extra", []):
            try:
                launcher_ids.append(int(i))
            except (ValueError, TypeError):
                pass

        if launcher_ids:
            ids[launcher] = launcher_ids

    if lutris := id_block.get("lutris"):
        ids["lutris"] = str(lutris)

    return ids


def sanitize_file_path(raw_path):
    normalized = re.sub(r'/{2,}', '/', raw_path.replace("\\", "/"))
    clean_path = replace_case_insensitive(normalized, ENV_RULES)

    return clean_path


def abstract_file_path(clean_path):
    return replace_case_insensitive(clean_path, MACRO_RULES)


def replace_case_insensitive(file_path, compiled_rules):
    for pattern, replacement in compiled_rules.items():
        file_path = pattern.sub(replacement, file_path)

    return file_path


# ==========================================
# MAIN EXECUTION
# ==========================================


def optimize_manifest():
    raw_yaml = get_raw_yaml()
    processed_manifest = {}

    total_games = 0
    valid_games = 0
    for game_name, game_data in raw_yaml.items():
        total_games += 1

        entry = {}

        if files := extract_files(game_data):
            entry["files"] = files

        if registry := extract_registry(game_data):
            entry["registry"] = registry

        if cloud := game_data.get("cloud", {}):
            entry["cloud"] = cloud

        if not entry:
            continue

        install_dir = extract_install_dir(game_data)

        if install_dir and install_dir != game_name:
            entry["installDir"] = install_dir

        if ids := extract_game_ids(game_data):
            entry["ids"] = ids

        valid_games += 1
        processed_manifest[game_name] = entry

    print(f"Processed {total_games:,} games")
    print(f"Found {valid_games:,} games with save data")

    try:
        with open(JSON_PATH, "w", encoding="utf-8") as tf:
            json.dump(processed_manifest, tf, separators=(',', ':'))
            #json.dump(processed_manifest, tf, indent=2)
    except OSError as e:
        print(f"Failed to save optimized code to {JSON_PATH}: {e}")

    print_size_reduction()


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
