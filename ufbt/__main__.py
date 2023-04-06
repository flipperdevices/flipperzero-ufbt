from . import ufbt_cli

if __name__ == "__main__":
    import sys

    sys.exit(ufbt_cli() or 0)
