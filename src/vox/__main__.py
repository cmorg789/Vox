"""CLI entrypoint for the Vox server."""

import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Vox server")
    parser.add_argument(
        "--host", default=os.environ.get("VOX_HOST", "127.0.0.1"), help="Bind address"
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("VOX_PORT", "8000")), help="Bind port"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("VOX_DATABASE_URL", "sqlite+aiosqlite:///vox.db"),
        help="SQLAlchemy async database URL",
    )
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    os.environ["VOX_DATABASE_URL"] = args.database_url

    uvicorn.run(
        "vox.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
