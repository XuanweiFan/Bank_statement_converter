"""
Entrypoint for running the local web server.
"""

import os

import uvicorn


def main() -> None:
    host = os.getenv("BSC_HOST", "127.0.0.1")
    port = int(os.getenv("BSC_PORT", "8000"))
    uvicorn.run("bank_statement_converter.web.app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
