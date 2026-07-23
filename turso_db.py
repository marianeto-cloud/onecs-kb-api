"""
Turso (libSQL) database module for OneCs KB API.
Uses libsql-client if available, falls back to HTTP API via urllib.
"""
import os
import json
from datetime import datetime

# ------------------------------------------------------------------
# Connection helpers
# ------------------------------------------------------------------

def _get_turso_config():
    """Read Turso configuration from environment variables."""
    db_url = os.environ.get("TURSO_DATABASE_URL", "")
    auth_token = os.environ.get("TURSO_AUTH_TOKEN", "")
    return db_url, auth_token


def _is_turso_configured():
    """Check if Turso is configured via environment variables."""
    db_url, auth_token = _get_turso_config()
    return bool(db_url and auth_token)


def _open_libsql_connection():
    """
    Open a libsql connection using the libsql-client package.
    Raises ImportError if the package is not available.
    """
    import libsql
    db_url, auth_token = _get_turso_config()
    return libsql.connect(db_url, auth_token=auth_token)


def _execute_via_http(sql, args=None, fetch=True):
    """
    Execute SQL via Turso HTTP API using urllib.
    Returns rows as list of dicts (column names as keys).
    """
    import urllib.request
    import urllib.error

    db_url, auth_token = _get_turso_config()

    # db_url format: libsql://[host]  →  need to strip scheme for HTTP API
    # HTTP API host: https://[host]/v2/pipeline
    http_url = db_url
    if http_url.startswith("libsql://"):
        http_url = "https://" + http_url[len("libsql://"):]
    http_url = http_url.rstrip("/") + "/v2/pipeline"

    body = {
        "statements": [
            {
                "stmt": sql,
                "args": args if args else []
            }
        ]
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        http_url,
        data=data,
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_resp = e.read().decode("utf-8")
        raise RuntimeError(f"Turso HTTP API error {e.code}: {body_resp}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Turso connection error: {e.reason}") from e

    # Parse results
    # Response format: {"results": [{"columns": [...], "rows": [...], "cols_changed": n}]}
    results = result.get("results", [])
    if not results:
        return []

    first = results[0]
    columns = first.get("columns", [])
    rows = first.get("rows", [])
    return [dict(zip(columns, row)) for row in rows]


def _execute_sql(sql, args=None, fetch=True):
    """
    Execute SQL using libsql if available, otherwise HTTP API.
    Returns rows when fetch=True, affected row count when fetch=False.
    """
    if _is_libsql_available():
        conn = _open_libsql_connection()
        cur = conn.cursor()
        cur.execute(sql, args or [])
        if fetch:
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in rows]
        else:
            conn.commit()
            return cur.rowcount if hasattr(cur, "rowcount") else conn.total_changes
    else:
        if fetch:
            return _execute_via_http(sql, args)
        else:
            # For non-fetch queries via HTTP, run without returning rows
            _execute_via_http(sql, args, fetch=False)
            return 0


def _is_libsql_available():
    """Check if libsql-client package is installed and importable."""
    try:
        import libsql  # noqa: F401
        return True
    except ImportError:
        return False


# ------------------------------------------------------------------
# Schema management
# ------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    categoria TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    tags TEXT,
    fonte TEXT DEFAULT 'api',
    data_criacao TEXT,
    status TEXT DEFAULT 'active'
);
"""


def init_db():
    """
    Create the knowledge_entries table if it does not exist.
    Uses libsql if available, otherwise HTTP API.
    """
    _execute_sql(CREATE_TABLE_SQL, fetch=False)
    if _is_turso_configured() and not _is_libsql_available():
        # HTTP API commits automatically
        pass
    else:
        conn = _open_libsql_connection()
        conn.commit()
        conn.close()


# ------------------------------------------------------------------
# CRUD operations
# ------------------------------------------------------------------

def list_entries():
    """
    Return all knowledge entries as summary (no full conteudo).
    Returns list of dicts.
    """
    sql = """
    SELECT id, titulo, categoria, tags, fonte, data_criacao, status
    FROM knowledge_entries
    ORDER BY id ASC;
    """
    rows = _execute_sql(sql)
    entries = []
    for row in rows:
        tags_val = row.get("tags", "")
        try:
            tags = json.loads(tags_val) if tags_val else []
        except json.JSONDecodeError:
            tags = []
        entries.append({
            "id": row.get("id"),
            "titulo": row.get("titulo"),
            "categoria": row.get("categoria"),
            "tags": tags,
            "fonte": row.get("fonte"),
            "data_criacao": row.get("data_criacao"),
            "status": row.get("status", "active"),
        })
    return entries


def get_entry(entry_id):
    """
    Return a single knowledge entry by ID (with full conteudo).
    Returns dict or None if not found.
    """
    sql = """
    SELECT id, titulo, categoria, conteudo, tags, fonte, data_criacao, status
    FROM knowledge_entries
    WHERE id = ?;
    """
    rows = _execute_sql(sql, args=[entry_id])
    if not rows:
        return None
    row = rows[0]
    tags_val = row.get("tags", "")
    try:
        tags = json.loads(tags_val) if tags_val else []
    except json.JSONDecodeError:
        tags = []
    return {
        "id": row.get("id"),
        "titulo": row.get("titulo"),
        "categoria": row.get("categoria"),
        "conteudo": row.get("conteudo"),
        "tags": tags,
        "fonte": row.get("fonte"),
        "data_criacao": row.get("data_criacao"),
        "status": row.get("status", "active"),
    }


def add_entry(data):
    """
    Insert a new knowledge entry.
    data is a dict with: titulo, categoria, conteudo, tags, fonte.
    Returns the created entry dict (with id and data_criacao).
    """
    sql = """
    INSERT INTO knowledge_entries (titulo, categoria, conteudo, tags, fonte, data_criacao, status)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    tags_json = json.dumps(data.get("tags", []), ensure_ascii=False)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    args = [
        data.get("titulo"),
        data.get("categoria"),
        data.get("conteudo"),
        tags_json,
        data.get("fonte", "api"),
        timestamp,
        "active",
    ]
    _execute_sql(sql, args=args, fetch=False)

    # Get the ID of the inserted row
    if _is_libsql_available():
        conn = _open_libsql_connection()
        cur = conn.cursor()
        cur.execute("SELECT last_insert_rowid() as id;")
        row = cur.fetchone()
        conn.close()
        new_id = row[0] if row else None
    else:
        # HTTP API: SELECT last_insert_rowid()
        rows = _execute_sql("SELECT last_insert_rowid() as id;")
        new_id = rows[0]["id"] if rows else None

    return {
        "id": new_id,
        "titulo": data.get("titulo"),
        "categoria": data.get("categoria"),
        "conteudo": data.get("conteudo"),
        "tags": data.get("tags", []),
        "fonte": data.get("fonte", "api"),
        "data_criacao": timestamp,
        "status": "active",
    }


def delete_entry(entry_id):
    """
    Delete a knowledge entry by ID.
    Returns True if deleted, False if not found.
    """
    sql = "DELETE FROM knowledge_entries WHERE id = ?;"
    _execute_sql(sql, args=[entry_id], fetch=False)

    # Verify deletion
    if get_entry(entry_id) is None:
        return True
    return False


def get_next_id():
    """
    Return the next available ID for a new entry.
    """
    sql = "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM knowledge_entries;"
    rows = _execute_sql(sql)
    if rows:
        return rows[0].get("next_id", 1)
    return 1


def count_entries():
    """Return the total number of entries in the table."""
    sql = "SELECT COUNT(*) AS cnt FROM knowledge_entries;"
    rows = _execute_sql(sql)
    if rows:
        return rows[0].get("cnt", 0)
    return 0


# ------------------------------------------------------------------
# Migration from JSON
# ------------------------------------------------------------------

def migrate_from_json(json_path):
    """
    Read entries from dynamic_knowledge.json and insert them into Turso
    if the table is empty (seed initial data).
    """
    import os
    if not os.path.exists(json_path):
        return

    if count_entries() > 0:
        # Table already has data, skip migration
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return

    if not isinstance(data, list):
        return

    for entry in data:
        tags_json = json.dumps(entry.get("tags", []), ensure_ascii=False)
        sql = """
        INSERT INTO knowledge_entries (titulo, categoria, conteudo, tags, fonte, data_criacao, status)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        args = [
            entry.get("titulo"),
            entry.get("categoria"),
            entry.get("conteudo"),
            tags_json,
            entry.get("fonte", "api"),
            entry.get("data_criacao"),
            entry.get("status", "active"),
        ]
        _execute_sql(sql, args=args, fetch=False)
