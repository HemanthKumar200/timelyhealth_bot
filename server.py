"""Timely Health chatbot API.

Run from the project root:

    .venv\\Scripts\\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
"""

from app.api.main import app

__all__ = ["app"]
