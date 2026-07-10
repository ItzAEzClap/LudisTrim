from manifest_manager import update_manifest
from manifest_optimizer import optimize_manifest


def main():
    if not update_manifest():
        return
    
    optimize_manifest()


if __name__ == "__main__":
    main()