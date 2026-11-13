from pathlib import Path

__version__ = "0.5.2"


def build_id() -> str:
    """Stamped by scripts/deploy.sh into openholter/BUILD ("20261030.0940"); "dev" when run from a checkout."""
    try:
        return (Path(__file__).parent / "BUILD").read_text().strip() or "dev"
    except OSError:
        return "dev"
