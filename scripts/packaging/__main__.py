"""Q-Guardian packaging utilities."""
import sys

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.packaging <build|validate>")
        sys.exit(1)
    command = sys.argv[1]
    if command == "build":
        from scripts.packaging.build import main as build_main
        build_main()
    elif command == "validate":
        from scripts.packaging.validate import main as validate_main
        validate_main()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
