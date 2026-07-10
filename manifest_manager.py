import urllib.request
import urllib.error
import logging
from pathlib import Path

BASE_DIR = Path("./resources")
ETAG_PATH = BASE_DIR / "manifest_etag"
YAML_PATH = BASE_DIR / "manifest.yaml"
JSON_PATH = BASE_DIR / "manifest.json"

LUDUSAVI_URL = "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/master/data/manifest.yaml"



def get_cached_etag() -> str:
    if ETAG_PATH.exists():
        try:
            return ETAG_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            logging.warning(f"Could not read cached ETag: {e}")
    return ""


def update_manifest(timeout=10) -> bool:
    headers = {}
    if etag := get_cached_etag():
        headers["If-None-Match"] = etag

    try:
        req = urllib.request.Request(LUDUSAVI_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as res:
            content = res.read().decode("utf-8")
            response_headers = res.headers
    except urllib.error.HTTPError as e:
        if e.code == 304:
            print("Manifest is already up to date.")
            return False
        logging.error(f"Network verification failed: HTTP {e.code}")
        return False
    except Exception as e:
        logging.error(f"Update connection failed: {e}")
        return False

    print("New update found! Saving files...")
    
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    tmp_yaml = YAML_PATH.with_suffix('.yaml.tmp')
    with open(tmp_yaml, "w", encoding="utf-8") as f:
        f.write(content)
    tmp_yaml.replace(YAML_PATH)

    if new_etag := response_headers.get("ETag"):
        try:
            ETAG_PATH.write_text(new_etag, encoding="utf-8")
        except OSError as e:
            logging.warning(f"Failed to save new ETag: {new_etag}")

    return True
