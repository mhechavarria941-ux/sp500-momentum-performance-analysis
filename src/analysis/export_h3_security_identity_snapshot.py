from __future__ import annotations

import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import pyodbc

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v2-h3-security-identity-snapshot-connection-fix"

OUT_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

SECURITY_PATH = OUT_DIR / "h3_core_security_snapshot.csv"
TICKER_HISTORY_PATH = OUT_DIR / "h3_core_security_ticker_history_snapshot.csv"
SECURITY_SCHEMA_PATH = OUT_DIR / "h3_core_security_schema.csv"
TICKER_SCHEMA_PATH = OUT_DIR / "h3_core_security_ticker_history_schema.csv"
REPORT_PATH = OUT_DIR / "h3_security_identity_snapshot_report.txt"
CONNECTION_DIAGNOSTIC_PATH = OUT_DIR / "h3_azure_connection_diagnostic.txt"

EXPECTED_SECURITY_ROWS = 593
EXPECTED_TICKER_HISTORY_ROWS = 594


def first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return default


def choose_driver() -> str:
    installed = set(pyodbc.drivers())

    for candidate in (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
    ):
        if candidate in installed:
            return candidate

    raise RuntimeError(
        "Microsoft ODBC Driver 17 or 18 for SQL Server is required. "
        f"Installed ODBC drivers: {sorted(installed)}"
    )


def normalize_server(raw_server: str) -> tuple[str, str, int]:
    """
    Accept common Azure SQL server representations and return:
    ODBC server value, hostname, port.
    """
    value = raw_server.strip()

    # If a user accidentally supplied SERVER=... style text, extract the value.
    match = re.search(
        r"(?:^|;)\s*server\s*=\s*([^;]+)",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        value = match.group(1).strip()

    # Remove surrounding braces if present.
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1].strip()

    # Normalize common ODBC tcp prefix.
    if value.lower().startswith("tcp:"):
        value = value[4:].strip()

    port = 1433
    hostname = value

    # Handle host,port.
    if "," in value:
        host_part, port_part = value.rsplit(",", 1)
        hostname = host_part.strip()
        try:
            port = int(port_part.strip())
        except ValueError:
            hostname = value
            port = 1433

    # Handle host:port only if it is a simple hostname form, not IPv6.
    elif value.count(":") == 1:
        host_part, port_part = value.rsplit(":", 1)
        if port_part.isdigit():
            hostname = host_part.strip()
            port = int(port_part)

    odbc_server = f"tcp:{hostname},{port}"
    return odbc_server, hostname, port


def redact_connection_string(connection_string: str) -> str:
    redacted = re.sub(
        r"(?i)(PWD|Password)\s*=\s*[^;]*",
        r"\1=***REDACTED***",
        connection_string,
    )
    redacted = re.sub(
        r"(?i)(UID|User ID|UserID)\s*=\s*[^;]*",
        r"\1=***REDACTED***",
        redacted,
    )
    return redacted


def tcp_probe(hostname: str, port: int, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with socket.create_connection(
            (hostname, port),
            timeout=timeout,
        ):
            return True, f"TCP connection to {hostname}:{port} succeeded."
    except Exception as exc:
        return False, (
            f"TCP connection to {hostname}:{port} failed: "
            f"{type(exc).__name__}: {exc}"
        )


def get_connection_candidates() -> tuple[list[str], dict]:
    """
    Build connection candidates without changing database state.

    Prefer an explicitly supplied full ODBC connection string if present.
    Otherwise construct standard Azure SQL SQL-auth strings from components.
    """
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")

    driver = choose_driver()

    full_string = first_env(
        "AZURE_SQL_CONNECTION_STRING",
        "SQL_CONNECTION_STRING",
        "ODBC_CONNECTION_STRING",
    )

    metadata = {
        "driver": driver,
        "connection_source": None,
        "server_raw": None,
        "server_odbc": None,
        "hostname": None,
        "port": None,
        "database": None,
        "username_present": False,
        "password_present": False,
    }

    candidates: list[str] = []

    if full_string:
        metadata["connection_source"] = "full_connection_string_env"
        candidates.append(full_string)

        # Try to extract server/database only for diagnostics.
        server_match = re.search(
            r"(?i)(?:^|;)\s*server\s*=\s*([^;]+)",
            full_string,
        )
        db_match = re.search(
            r"(?i)(?:^|;)\s*(?:database|initial catalog)\s*=\s*([^;]+)",
            full_string,
        )
        if server_match:
            raw_server = server_match.group(1).strip()
            metadata["server_raw"] = raw_server
            try:
                server_odbc, hostname, port = normalize_server(raw_server)
                metadata["server_odbc"] = server_odbc
                metadata["hostname"] = hostname
                metadata["port"] = port
            except Exception:
                pass
        if db_match:
            metadata["database"] = db_match.group(1).strip()

        return candidates, metadata

    server = first_env(
        "AZURE_SQL_SERVER",
        "SQL_SERVER",
        "DB_SERVER",
        "DATABASE_SERVER",
    )
    database = first_env(
        "AZURE_SQL_DATABASE",
        "SQL_DATABASE",
        "DB_NAME",
        "DATABASE_NAME",
        default="sp500_analytics",
    )
    username = first_env(
        "AZURE_SQL_USERNAME",
        "SQL_USERNAME",
        "DB_USER",
        "DATABASE_USERNAME",
    )
    password = first_env(
        "AZURE_SQL_PASSWORD",
        "SQL_PASSWORD",
        "DB_PASSWORD",
        "DATABASE_PASSWORD",
    )

    missing = [
        label
        for label, value in (
            ("server", server),
            ("username", username),
            ("password", password),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing database setting(s): "
            + ", ".join(missing)
            + ". Supported env names include "
            "AZURE_SQL_SERVER/AZURE_SQL_DATABASE/"
            "AZURE_SQL_USERNAME/AZURE_SQL_PASSWORD."
        )

    server_odbc, hostname, port = normalize_server(server)

    metadata.update(
        {
            "connection_source": "component_env_vars",
            "server_raw": server,
            "server_odbc": server_odbc,
            "hostname": hostname,
            "port": port,
            "database": database,
            "username_present": bool(username),
            "password_present": bool(password),
        }
    )

    # IMPORTANT:
    # Do not wrap SERVER/DATABASE/UID in braces. Driver is the only value that
    # needs braces here. Password uses ODBC braced escaping only when needed.
    def safe_password(value: str) -> str:
        if ";" in value or value.startswith("{") or value.endswith("}"):
            return "{" + value.replace("}", "}}") + "}"
        return value

    pwd = safe_password(password)

    base = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server_odbc};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={pwd};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=60;"
    )

    # Candidate 1: standard SQL-auth Azure string.
    candidates.append(base)

    # Candidate 2: explicitly declare SQL password authentication.
    if "ODBC Driver 18 for SQL Server" in driver:
        candidates.append(
            base
            + "Authentication=SqlPassword;"
        )

    return candidates, metadata


def connect() -> pyodbc.Connection:
    candidates, metadata = get_connection_candidates()

    diagnostic_lines = [
        "=" * 104,
        "H3 AZURE SQL CONNECTION DIAGNOSTIC",
        "=" * 104,
        f"Script version: {SCRIPT_VERSION}",
        f"Connection source: {metadata.get('connection_source')}",
        f"ODBC driver: {metadata.get('driver')}",
        f"Server (raw): {metadata.get('server_raw')}",
        f"Server (normalized): {metadata.get('server_odbc')}",
        f"Hostname: {metadata.get('hostname')}",
        f"Port: {metadata.get('port')}",
        f"Database: {metadata.get('database')}",
        f"Username present: {metadata.get('username_present')}",
        f"Password present: {metadata.get('password_present')}",
        "",
    ]

    hostname = metadata.get("hostname")
    port = metadata.get("port")

    if hostname and port:
        tcp_ok, tcp_message = tcp_probe(
            str(hostname),
            int(port),
        )
        diagnostic_lines.append(
            "TCP probe: " + ("PASS" if tcp_ok else "FAIL")
        )
        diagnostic_lines.append(tcp_message)
        diagnostic_lines.append("")
    else:
        tcp_ok = None
        diagnostic_lines.append(
            "TCP probe: SKIPPED (hostname could not be extracted)"
        )
        diagnostic_lines.append("")

    errors = []

    for index, connection_string in enumerate(candidates, start=1):
        diagnostic_lines.append(
            f"Connection candidate {index}: "
            + redact_connection_string(connection_string)
        )

        try:
            conn = pyodbc.connect(
                connection_string,
                autocommit=True,
                timeout=60,
            )
            diagnostic_lines.append(
                f"Candidate {index}: CONNECTION SUCCEEDED"
            )
            diagnostic_lines.append("")
            CONNECTION_DIAGNOSTIC_PATH.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            CONNECTION_DIAGNOSTIC_PATH.write_text(
                "\n".join(diagnostic_lines) + "\n",
                encoding="utf-8",
            )
            return conn
        except pyodbc.Error as exc:
            message = str(exc)
            errors.append(message)
            diagnostic_lines.append(
                f"Candidate {index}: CONNECTION FAILED"
            )
            diagnostic_lines.append(message)
            diagnostic_lines.append("")

    diagnostic_lines += [
        "FINAL RESULT: AZURE SQL CONNECTION FAILED",
        "",
    ]

    if tcp_ok is False:
        diagnostic_lines += [
            "Likely category: NETWORK / AZURE FIREWALL / SERVER AVAILABILITY.",
            (
                "The machine could not open a TCP connection to the Azure SQL "
                "server on port 1433. Check Azure SQL firewall/network access, "
                "VPN/network restrictions, and whether the logical SQL server "
                "is online."
            ),
        ]
    elif tcp_ok is True:
        diagnostic_lines += [
            "Likely category: ODBC CONNECTION STRING / AUTHENTICATION.",
            (
                "TCP port 1433 is reachable, so the failure is more likely "
                "connection-string or credential/authentication related."
            ),
        ]
    else:
        diagnostic_lines += [
            "Likely category: CONNECTION STRING OR SERVER VALUE.",
        ]

    CONNECTION_DIAGNOSTIC_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    CONNECTION_DIAGNOSTIC_PATH.write_text(
        "\n".join(diagnostic_lines) + "\n",
        encoding="utf-8",
    )

    raise RuntimeError(
        "Azure SQL connection failed. "
        f"A redacted diagnostic was written to:\n{CONNECTION_DIAGNOSTIC_PATH}\n"
        "This V2 script does not modify the database."
    )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with connect() as conn:
        security = pd.read_sql_query(
            "SELECT * FROM core.security ORDER BY 1;",
            conn,
        )
        ticker_history = pd.read_sql_query(
            "SELECT * FROM core.security_ticker_history ORDER BY 1;",
            conn,
        )

        security_schema = pd.read_sql_query(
            """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                IS_NULLABLE,
                ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'core'
              AND TABLE_NAME = 'security'
            ORDER BY ORDINAL_POSITION;
            """,
            conn,
        )

        ticker_schema = pd.read_sql_query(
            """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                IS_NULLABLE,
                ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'core'
              AND TABLE_NAME = 'security_ticker_history'
            ORDER BY ORDINAL_POSITION;
            """,
            conn,
        )

    security.to_csv(
        SECURITY_PATH,
        index=False,
    )
    ticker_history.to_csv(
        TICKER_HISTORY_PATH,
        index=False,
    )
    security_schema.to_csv(
        SECURITY_SCHEMA_PATH,
        index=False,
    )
    ticker_schema.to_csv(
        TICKER_SCHEMA_PATH,
        index=False,
    )

    if len(security) != EXPECTED_SECURITY_ROWS:
        raise RuntimeError(
            f"core.security rows={len(security)}, "
            f"expected {EXPECTED_SECURITY_ROWS}."
        )

    if len(ticker_history) != EXPECTED_TICKER_HISTORY_ROWS:
        raise RuntimeError(
            f"core.security_ticker_history rows={len(ticker_history)}, "
            f"expected {EXPECTED_TICKER_HISTORY_ROWS}."
        )

    lines = [
        "=" * 106,
        "H3 SECURITY IDENTITY SNAPSHOT",
        "=" * 106,
        f"core.security rows: {len(security)}",
        f"core.security_ticker_history rows: {len(ticker_history)}",
        f"core.security columns: {len(security.columns)}",
        (
            "core.security_ticker_history columns: "
            f"{len(ticker_history.columns)}"
        ),
        "Database modifications: 0",
        "Return/outcome fields queried: 0",
        "",
        "Security columns:",
        " | ".join(map(str, security.columns)),
        "",
        "Ticker-history columns:",
        " | ".join(map(str, ticker_history.columns)),
        "",
        "H3_SECURITY_IDENTITY_SNAPSHOT_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        text,
        encoding="utf-8",
    )
    print(text, end="")


if __name__ == "__main__":
    main()
