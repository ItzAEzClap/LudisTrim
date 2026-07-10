import config
import manifest_manager
import time
import os


import json

def calculate_size_reduction() -> None:
    raw_size_bytes = os.path.getsize(config.YAML_FILE_PATH)
    opt_size_bytes = os.path.getsize(config.JSON_FILE_PATH)

    print(f"Raw Manifest Size:       {raw_size_bytes / 1024:.2f} KB")
    print(f"Optimized Manifest Size: {opt_size_bytes / 1024:.2f} KB")
    
    reduction_percentage = ((raw_size_bytes - opt_size_bytes) / raw_size_bytes) * 100
    print(f"Reduction:                {reduction_percentage:.1f}% smaller")


def main():
    if manifest_manager.sync_manifest():
        manifest = manifest_manager.load_manifest()

    profile = config.load_user_config()

    calculate_size_reduction()
    
"""
    discovered_roots = None
    if not os.path.exists(config.CONFIG_FILE):
        print("\nFirst run detected. Mapping local storage locations for digital storefronts...")
        discovered_roots = scanner.scan_system_for_launchers()

    user_config = config.load_or_create_user_config(discovered_roots)
    active_roots = user_config["roots"]

    print(f"It took {time.perf_counter() - start_init:.4f} seconds to initialize manifest and config.")

    print("\nScanning local drives for installed games...")

    start_scan = time.perf_counter()
    game_finder.find_local_savefiles(manifest, active_roots)
    print(f"It took: {time.perf_counter() - start_scan:.4f} seconds to find all game saves.")
"""
if __name__ == "__main__":
    main()