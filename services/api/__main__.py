"""Environment-configured SCAMSTAGE server entry point."""

import uvicorn

from services.api.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run("services.api.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
