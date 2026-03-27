import os
import socket
import sys
import time

import psycopg2


def main() -> int:
    host = os.getenv("DB_HOST", "db")
    port = int(os.getenv("DB_PORT", "5432"))
    dbname = os.getenv("DB_NAME", "myscience_db")
    user = os.getenv("DB_USER", "myscience_user")
    password = os.getenv("DB_PASSWORD", "myscience_password")
    timeout_seconds = int(os.getenv("DB_WAIT_TIMEOUT", "60"))
    retry_interval = float(os.getenv("DB_WAIT_INTERVAL", "2"))

    deadline = time.time() + timeout_seconds
    last_error = ""

    while time.time() < deadline:
        try:
            # Resolve the Compose service name before opening a DB connection.
            socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            conn = psycopg2.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port,
                connect_timeout=5,
            )
            conn.close()
            print(f"Database is ready at {host}:{port}")
            return 0
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            print(f"Waiting for database at {host}:{port}: {last_error}", flush=True)
            time.sleep(retry_interval)

    print(
        f"Database did not become ready within {timeout_seconds}s. Last error: {last_error}",
        file=sys.stderr,
        flush=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
