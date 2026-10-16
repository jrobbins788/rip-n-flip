"""Fail fast when MongoDB is unreachable, and hide the raw driver error.

Production was spending the driver's default 30s server-selection timeout
and then crashing the request as a text/plain 500. The app process only
starts when MONGO_URL and DB_NAME are set, so a hang means the configured
host never answers (wrong URL, paused cluster, or a network allow-list
that does not include Railway).

These timeouts do not fix a bad MONGO_URL. They make the failure a normal
JSON response in a few seconds instead of an unhandled 500.

Railway service variables that must point at a reachable database:

    MONGO_URL=mongodb+srv://<user>:<password>@<cluster>/<db>?retryWrites=true&w=majority
    DB_NAME=<database name>

If the host is Atlas, its Network Access list has to allow this service
(or 0.0.0.0/0). A paused cluster looks the same as a refused connection.
"""
from __future__ import annotations

import asyncio

from pymongo.errors import PyMongoError

# Just under the per-call wait below, so the driver raises a real
# ServerSelectionTimeoutError (host, DNS, TLS) that we can log.
MONGO_SERVER_SELECTION_TIMEOUT_MS = 8000
MONGO_CONNECT_TIMEOUT_MS = 8000
DB_OPERATION_TIMEOUT_SECONDS = 10.0


class DatabaseUnavailable(Exception):
    """MongoDB could not be reached or did not answer in time."""


def mongo_client_kwargs() -> dict:
    return {
        "serverSelectionTimeoutMS": MONGO_SERVER_SELECTION_TIMEOUT_MS,
        "connectTimeoutMS": MONGO_CONNECT_TIMEOUT_MS,
    }


async def await_db(awaitable, *, timeout: float = DB_OPERATION_TIMEOUT_SECONDS):
    """Await a Motor operation, converting outages into DatabaseUnavailable."""
    try:
        return await asyncio.wait_for(awaitable, timeout)
    except TimeoutError as exc:
        raise DatabaseUnavailable(
            f"MongoDB did not respond within {timeout:.0f}s"
        ) from exc
    except PyMongoError as exc:
        detail = str(exc).strip() or type(exc).__name__
        raise DatabaseUnavailable(detail) from exc
