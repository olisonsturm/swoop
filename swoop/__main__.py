"""Entry point for `python -m swoop`."""

try:
    from swoop.cli import main
except ImportError as e:
    import sys
    print(
        "Error: CLI dependencies not installed.\n"
        "Install them with: pip install swoop-flights[cli]\n"
        f"\nMissing: {e}",
        file=sys.stderr,
    )
    sys.exit(1)

main()
