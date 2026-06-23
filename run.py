"""Entry point: launch the Human Memory Agent web server."""

from __future__ import annotations

import uvicorn

from app.config import settings


def main() -> None:
    print(f"Human Memory Agent -> http://{settings.host}:{settings.port}")
    print(f"  LLM   : {settings.chat_model} @ {settings.llm_base_url}")
    print(f"  Embed : {settings.embed_model} (dim={settings.embed_dim})")
    print(f"  Data  : {settings.data_dir.resolve()}")
    uvicorn.run("app.api:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
