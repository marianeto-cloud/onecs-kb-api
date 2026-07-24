"""
Turso (libSQL) database module for OneCs KB API.

Usa o pacote oficial `libsql` quando disponível (ligação direta, rápida e
com tipos corretos). Se por algum motivo não estiver instalado, cai para
uma implementação manual sobre a HTTP API v2/pipeline do Turso via urllib.

Tabelas geridas por este módulo:
  - knowledge_entries: conhecimento dinâmico (add_knowledge / list / get / delete)
  - topic_versions:    histórico de versões de tópicos (para poder reverter)
  - topic_overrides:   conteúdo ATIVO de um tópico depois de ser atualizado
                        (substitui o ficheiro estático enquanto o servidor
                        estiver a usar Turso — sem isto, uma atualização de
                        tópico perder-se-ia a cada redeploy no Render free tier)
"""
import os
import json
from datetime import datetime, timezone

# ------------------------------------------------------------------
# Connection helpers
# ------------------------------------------------------------------

def _get_turso_config():
    """Read Turso configuration from environment variables.

    .strip() é importante aqui: colar as credenciais no Render (ou no
    terminal) facilmente introduz um espaço ou quebra de linha invisível
    no início/fim do valor, o que corrompe o URL e o header Authorization
    sem dar um erro óbvio.
    """
    db_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    auth_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    return db_url, auth_token


def _is_turso_configured():
    """Check if Turso is configured via environment variables."""
    db_url, auth_token = _get_turso_config()
    return bool(db_url and auth_token)


def _is_libsql_available():
    """Check if the official `libsql` package is installed and importable."""
    try:
        import libsql  # noqa: F401
        return True
    except ImportError:
        return False


def _open_libsql_connection():
    """
    Open a libsql connection using the official `libsql` package.
    Raises ImportError if the package is not available.
    """
    import libsql
    db_url, auth_token = _get_turso_config()
    return libsql.connect(database=db_url, auth_token=auth_token)


# ------------------------------------------------------------------
# Turso HTTP v2 / pipeline helpers (fallback quando `libsql` não está instalado)
# ------------------------------------------------------------------

def _convert_args(args):
    """
    Convert a list of plain Python values to Turso typed format.

    Turso v2 typed values:
      str  → {"type": "text",   "value": val}
      int  → {"type": "integer","value": val}
      float→ {"type": "float",  "value": val}
      None → {"type": "null"}
      bool → {"type": "integer","value": 1 if val else 0}
    """
    if args is None:
        return []
    typed = []
    for val in args:
        if val is None:
            typed.append({"type": "null"})
        elif isinstance(val, bool):
            typed.append({"type": "integer", "value": 1 if val else 0})
        elif isinstance(val, int):
            typed.append({"type": "integer", "value": val})
        elif isinstance(val, float):
            typed.append({"type": "float", "value": val})
        else:
            typed.append({"type": "text", "value": str(val)})
    return typed


def _decode_typed_value(cell):
    """Converte uma célula tipada do Turso (ex: {"type": "integer", "value": "1"})
    de volta para o tipo Python nativo correto.

    IMPORTANTE: o Turso devolve "integer" e "float" com o valor como STRING
    (para não perder precisão em inteiros de 64 bits). Sem esta conversão,
    algo como COUNT(*) chega como a string "0" em vez do número 0, o que
    depois rebenta em comparações como `count_entries() > 0`
    (TypeError: '>' not supported between instances of 'str' and 'int').
    """
    cell_type = cell.get("type")
    value = cell.get("value")

    if cell_type == "null" or value is None:
        return None
    if cell_type == "integer":
        return int(value)
    if cell_type == "float":
        return float(value)
    # "text", "blob" e quaisquer outros tipos ficam como vieram (string)
    return value


def _execute_via_http(sql, args=None):
    """
    Execute SQL via Turso HTTP v2/pipeline API using urllib.
    Returns rows as list of dicts (column names as keys), com os valores
    já convertidos para os tipos Python corretos (int/float/None/str).
    """
    import urllib.request
    import urllib.error

    db_url, auth_token = _get_turso_config()

    # db_url format: libsql://[host]  →  need to strip scheme for HTTP API
    # HTTP API host: https://[host]/v2/pipeline
    http_url = db_url
    if http_url.startswith("libsql://"):
        http_url = "https://" + http_url[len("libsql://"):]
    http_url = http_url.rstrip("/")
    # Proteção extra: se a variável de ambiente já incluir "/v2/pipeline"
    # por engano, não duplicamos o sufixo.
    if not http_url.endswith("/v2/pipeline"):
        http_url = http_url + "/v2/pipeline"

    typed_args = _convert_args(args)
    body = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": typed_args,
                }
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

    results = result.get("results", [])
    if not results:
        return []

    first = results[0]
    if first.get("type") != "ok":
        error_msg = first.get("response", {}).get("error", str(first))
        raise RuntimeError(f"Turso HTTP API error: {error_msg}")

    res_data = first.get("response", {})
    result_obj = res_data.get("result", {})
    cols_meta = result_obj.get("cols", [])
    rows_typed = result_obj.get("rows", [])

    columns = [col.get("name") for col in cols_meta]

    rows = []
    for row in rows_typed:
        values = [_decode_typed_value(cell) for cell in row]
        rows.append(dict(zip(columns, values)))

    return rows


def _execute(sql, args=None, commit=False):
    """
    Executa uma instrução SQL, devolvendo sempre uma lista de dicts
    (mesmo para INSERT/UPDATE/DELETE com RETURNING, ou lista vazia
    para instruções sem RETURNING).

    Usa o pacote `libsql` quando disponível; caso contrário usa a HTTP API.
    Esta função única substitui os antigos `_execute_sql`/`fetch=True|False`
    para eliminar a ambiguidade que causava bugs (ex: usar duas ligações
    separadas para INSERT + last_insert_rowid()).
    """
    if _is_libsql_available():
        conn = _open_libsql_connection()
        try:
            cur = conn.execute(sql, args or [])
            rows = []
            if cur.description is not None:
                columns = [col[0] for col in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            if commit:
                conn.commit()
            return rows
        finally:
            conn.close()
    else:
        return _execute_via_http(sql, args)


# ------------------------------------------------------------------
# Schema management
# ------------------------------------------------------------------

CREATE_KNOWLEDGE_TABLE_SQL = """
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

CREATE_TOPIC_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS topic_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    product TEXT NOT NULL,
    version TEXT,
    nota TEXT,
    conteudo_backup TEXT NOT NULL,
    data_atualizacao TEXT
);
"""

CREATE_TOPIC_OVERRIDES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS topic_overrides (
    topic TEXT NOT NULL,
    product TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    atualizado_em TEXT,
    PRIMARY KEY (topic, product)
);
"""


def init_db():
    """
    Create all required tables if they do not exist yet.
    """
    _execute(CREATE_KNOWLEDGE_TABLE_SQL, commit=True)
    _execute(CREATE_TOPIC_VERSIONS_TABLE_SQL, commit=True)
    _execute(CREATE_TOPIC_OVERRIDES_TABLE_SQL, commit=True)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------
# CRUD: conhecimento dinâmico
# ------------------------------------------------------------------

def list_entries():
    """Return all knowledge entries as summary (no full conteudo)."""
    sql = """
    SELECT id, titulo, categoria, tags, fonte, data_criacao, status
    FROM knowledge_entries
    ORDER BY id ASC;
    """
    rows = _execute(sql)
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
    """Return a single knowledge entry by ID (with full conteudo), or None."""
    sql = """
    SELECT id, titulo, categoria, conteudo, tags, fonte, data_criacao, status
    FROM knowledge_entries
    WHERE id = ?;
    """
    rows = _execute(sql, args=[entry_id])
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

    Usa "RETURNING id" para obter o novo ID na MESMA operação que faz o
    INSERT — evita uma ronda extra a perguntar last_insert_rowid(), que era
    arriscado sob concorrência (podia devolver o ID de OUTRO pedido em
    simultâneo, já que cada chamada HTTP é uma ligação nova).
    """
    tags_json = json.dumps(data.get("tags", []), ensure_ascii=False)
    timestamp = _now_iso()
    sql = """
    INSERT INTO knowledge_entries (titulo, categoria, conteudo, tags, fonte, data_criacao, status)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    RETURNING id;
    """
    args = [
        data.get("titulo"),
        data.get("categoria"),
        data.get("conteudo"),
        tags_json,
        data.get("fonte", "api"),
        timestamp,
        "active",
    ]
    rows = _execute(sql, args=args, commit=True)
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
    Returns True if a row was actually deleted, False if it didn't exist.

    Usa "RETURNING id" para saber, na mesma operação, se algo foi mesmo
    apagado — evita uma segunda chamada de verificação.
    """
    sql = "DELETE FROM knowledge_entries WHERE id = ? RETURNING id;"
    rows = _execute(sql, args=[entry_id], commit=True)
    return len(rows) > 0


def count_entries():
    """Return the total number of entries in the table (int)."""
    sql = "SELECT COUNT(*) AS cnt FROM knowledge_entries;"
    rows = _execute(sql)
    if rows:
        return rows[0].get("cnt", 0)
    return 0


# ------------------------------------------------------------------
# Migração inicial a partir do dynamic_knowledge.json
# ------------------------------------------------------------------

def migrate_from_json(json_path):
    """
    Read entries from dynamic_knowledge.json and insert them into Turso
    if the table is empty (seed initial data). Não faz nada se a tabela
    já tiver dados (evita duplicar entradas em cada arranque).
    """
    if not os.path.exists(json_path):
        return

    if count_entries() > 0:
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return

    if not isinstance(data, list):
        return

    sql = """
    INSERT INTO knowledge_entries (titulo, categoria, conteudo, tags, fonte, data_criacao, status)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    for entry in data:
        tags_json = json.dumps(entry.get("tags", []), ensure_ascii=False)
        args = [
            entry.get("titulo"),
            entry.get("categoria"),
            entry.get("conteudo"),
            tags_json,
            entry.get("fonte", "api"),
            entry.get("data_criacao"),
            entry.get("status", "active"),
        ]
        _execute(sql, args=args, commit=True)


# ------------------------------------------------------------------
# CRUD: versionamento de tópicos (novo — antes só existia em ficheiros
# locais, que se perdiam a cada redeploy no Render free tier)
# ------------------------------------------------------------------

def add_version(topic, product, version, nota, conteudo_backup):
    """Guarda uma cópia do conteúdo ANTERIOR de um tópico, antes de o
    atualizar ou reverter. Devolve o id da versão criada."""
    sql = """
    INSERT INTO topic_versions (topic, product, version, nota, conteudo_backup, data_atualizacao)
    VALUES (?, ?, ?, ?, ?, ?)
    RETURNING id;
    """
    args = [topic, product, version, nota, conteudo_backup, _now_iso()]
    rows = _execute(sql, args=args, commit=True)
    return rows[0]["id"] if rows else None


def list_versions():
    """Lista todas as versões guardadas de todos os tópicos (sem o
    conteúdo completo do backup), mais recente primeiro."""
    sql = """
    SELECT id, topic, product, version, nota, data_atualizacao
    FROM topic_versions
    ORDER BY data_atualizacao DESC;
    """
    return _execute(sql)


def list_versions_for_topic(topic):
    """Lista as versões guardadas de um tópico específico, mais recente
    primeiro."""
    sql = """
    SELECT id, topic, product, version, nota, data_atualizacao
    FROM topic_versions
    WHERE topic = ?
    ORDER BY data_atualizacao DESC;
    """
    return _execute(sql, args=[topic])


def get_version_backup(topic, version):
    """Devolve o registo mais recente (com o conteúdo do backup incluído)
    para o par (topic, version), ou None se não existir."""
    sql = """
    SELECT id, topic, product, version, nota, conteudo_backup, data_atualizacao
    FROM topic_versions
    WHERE topic = ? AND version = ?
    ORDER BY data_atualizacao DESC
    LIMIT 1;
    """
    rows = _execute(sql, args=[topic, version])
    return rows[0] if rows else None


# ------------------------------------------------------------------
# CRUD: conteúdo ATIVO de tópicos atualizados (overrides)
# ------------------------------------------------------------------

def upsert_override(topic, product, conteudo):
    """Substitui (ou cria) o conteúdo ativo de um tópico atualizado."""
    sql = """
    INSERT INTO topic_overrides (topic, product, conteudo, atualizado_em)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(topic, product) DO UPDATE SET
        conteudo = excluded.conteudo,
        atualizado_em = excluded.atualizado_em;
    """
    _execute(sql, args=[topic, product, conteudo, _now_iso()], commit=True)


def get_override(topic, product):
    """Devolve o conteúdo ativo (override) de um tópico, ou None se o
    tópico nunca tiver sido atualizado via update_topic."""
    sql = """
    SELECT conteudo FROM topic_overrides WHERE topic = ? AND product = ?;
    """
    rows = _execute(sql, args=[topic, product])
    return rows[0]["conteudo"] if rows else None
