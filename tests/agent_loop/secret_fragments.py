"""Build secret-like test candidates at runtime from fragments.

Committed sources must not contain full scanner-matching literals so the
productive PR diff stays clean for secret_scan.py (no path allowlists).
"""

from __future__ import annotations


def api_key_assignment(value: str = "abc") -> str:
    return "api" + "_key" + "=" + value


def aws_access_key_id() -> str:
    return "AKIA" + ("0" * 16)


def aws_secret_access_key_assignment(value: str = "xyz") -> str:
    return "aws" + "_secret" + "_access" + "_key" + "=" + value


def private_key_begin(kind: str = "RSA") -> str:
    # kind examples: "RSA", "EC", "OPENSSH" (OPENSSH includes trailing space in join)
    if kind == "OPENSSH":
        return "-----BEGIN " + "OPENSSH " + "PRIVATE KEY-----"
    if kind == "EC":
        return "-----BEGIN " + "EC " + "PRIVATE KEY-----"
    return "-----BEGIN " + "RSA " + "PRIVATE KEY-----"


def private_key_end(kind: str = "RSA") -> str:
    if kind == "OPENSSH":
        return "-----END " + "OPENSSH " + "PRIVATE KEY-----"
    if kind == "EC":
        return "-----END " + "EC " + "PRIVATE KEY-----"
    return "-----END " + "RSA " + "PRIVATE KEY-----"


def bearer_token(token: str = "abcdefghijklmnop") -> str:
    return "Authorization: " + "Bearer " + token


def postgres_url(
    user: str = "user",
    password: str = "pass",
    host: str = "localhost",
    db: str = "db",
) -> str:
    return "postgres" + "://" + user + ":" + password + "@" + host + "/" + db


def sqlalchemy_postgres_url(
    dialect: str = "psycopg",
    user: str = "user",
    password: str = "pass",
    host: str = "localhost",
    db: str = "db",
) -> str:
    return "postgresql" + "+" + dialect + "://" + user + ":" + password + "@" + host + "/" + db


def mysql_url(
    user: str = "user",
    password: str = "pass",
    host: str = "localhost",
    db: str = "db",
) -> str:
    return "mysql" + "://" + user + ":" + password + "@" + host + "/" + db


def mongodb_url(
    user: str = "user",
    password: str = "pass",
    host: str = "localhost",
    db: str = "db",
) -> str:
    return "mongodb" + "://" + user + ":" + password + "@" + host + "/" + db


def database_url_assignment(
    scheme: str = "customdb",
    user: str = "user",
    password: str = "pass",
    host: str = "localhost",
    db: str = "db",
) -> str:
    return (
        "DATABASE"
        + "_URL="
        + scheme
        + "://"
        + user
        + ":"
        + password
        + "@"
        + host
        + "/"
        + db
    )


def railway_token_assignment(value: str = "tok_abc123") -> str:
    return "RAILWAY" + "_TOKEN" + "=" + value


def session_secret_assignment(value: str = "session_value_here") -> str:
    return "SESSION" + "_SECRET" + "=" + value


def github_pat() -> str:
    return "ghp" + "_" + ("a" * 20)


def slack_token() -> str:
    return "xoxb" + "-" + ("a" * 12)


def openai_sk() -> str:
    return "sk" + "-" + ("a" * 20)


def secret_diff_text() -> str:
    """Synthetic unified diff that trips multiple secret_scan families."""
    lines = [
        "diff --git a/config.env b/config.env",
        "index 1111111..2222222 100644",
        "--- a/config.env",
        "+++ b/config.env",
        "@@ -1,2 +1,8 @@",
        "+" + api_key_assignment("secret123"),
        "+" + "DATABASE" + "_URL=" + postgres_url(),
        "+"
        + "SQLALCHEMY_URL="
        + sqlalchemy_postgres_url(password="supersecret"),
        "+"
        + "ASYNC_URL="
        + sqlalchemy_postgres_url(dialect="asyncpg", password="asyncpass"),
        "+" + railway_token_assignment("railway_tok_abc123"),
        "+" + session_secret_assignment("session_supersecret_value"),
        " APP_ENV=test",
        "",
    ]
    return "\n".join(lines)


def secret_sqlalchemy_diff_text() -> str:
    lines = [
        "diff --git a/db.py b/db.py",
        "index 1111111..2222222 100644",
        "--- a/db.py",
        "+++ b/db.py",
        "@@ -1,2 +1,3 @@",
        "+# sqlalchemy URL with embedded password",
        '+'
        + 'engine = create_engine("'
        + sqlalchemy_postgres_url(
            user="app", password="hunter2", host="db.example", db="prod"
        )
        + '")',
        ' print("ok")',
        "",
    ]
    return "\n".join(lines)
