"""Compatibility wrapper. Use scripts/evaluate.py for accuracy checks."""
from app.rag.engine import *  # noqa: F403
from app.rag.engine import main

if __name__ == "__main__":
    main()
