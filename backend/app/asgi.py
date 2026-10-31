"""ASGI entry point: ``gunicorn app.asgi:app -k uvicorn.workers.UvicornWorker``."""

from app.main import create_app

app = create_app()
