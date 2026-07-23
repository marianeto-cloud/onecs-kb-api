"""
MCP Server for OneCs KB API
============================
Implements the Model Context Protocol (MCP) JSON-RPC 2.0 over HTTP.
Streamable HTTP transport — no external MCP package dependencies.

Supports:
  - initialize    (handshake)
  - ping          (keep-alive)
  - tools/list    (enumerate available tools)
  - tools/call    (invoke a named tool with arguments)
  - resources/list (enumerate wiki files as resources)
  - resources/read (fetch a specific resource URI)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Optional

# ------------------------------------------------------------------
# Module-level references to app state (set once by app.py)
# ------------------------------------------------------------------
_wiki_data_dir: str = ""
versions_dir: str = ""
dynamic_knowledge_file: str = ""
_products: list[str] = []


def init_mcp(base_dir: str, wiki_data_dir: str, versions: str, dynamic_kb: str, products: list[str]):
    """Called by app.py at startup to inject configuration."""
    global _wiki_data_dir, versions_dir, dynamic_knowledge_file, _products
    _wiki_data_dir = wiki_data_dir
    versions_dir = versions
    dynamic_knowledge_file = dynamic_kb
    _products = products


# ------------------------------------------------------------------
# Helpers (mirror app.py logic)
# ------------------------------------------------------------------

def _turso_available() -> bool:
    return bool(os.environ.get("TURSO_DATABASE_URL", "")) and bool(
        os.environ.get("TURSO_AUTH_TOKEN", "")
    )


def _load_all_markdown() -> dict:
    """Load all wiki markdown files keyed by relative path."""
    all_content = {}
    for product in _products:
        product_dir = os.path.join(_wiki_data_dir, product)
        if os.path.isdir(product_dir):
            for fname in os.listdir(product_dir):
                if fname.endswith(".md"):
                    rel = os.path.join(product, fname)
                    full_path = os.path.join(product_dir, fname)
                    with open(full_path, "r", encoding="utf-8") as f:
                        all_content[rel] = {
                            "content": f.read(),
                            "product": product,
                        }
    return all_content


def _find_topic_file(topic: str):
    """Find the file for a given topic across all product directories."""
    for product in _products:
        product_dir = os.path.join(_wiki_data_dir, product)
        if os.path.isdir(product_dir):
            path = os.path.join(product_dir, f"{topic}.md")
            if os.path.exists(path):
                return path, product
            for fname in os.listdir(product_dir):
                if fname.lower() == f"{topic}.md".lower():
                    return os.path.join(product_dir, fname), product
    return None, None


def _search_content(query: str, all_content: dict, product_filter: Optional[str] = None) -> list[dict]:
    """Simple keyword search across wiki pages."""
    query_lower = query.lower()
    results = []
    for filename, data in all_content.items():
        if product_filter and data["product"] != product_filter:
            continue
        content = data["content"]
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                snippet = "\n".join(lines[start:end])
                results.append({
                    "file": filename,
                    "product": data["product"],
                    "line": i + 1,
                    "snippet": snippet.strip(),
                })
    return results


def _load_dynamic_knowledge() -> list:
    if not os.path.exists(dynamic_knowledge_file):
        return []
    try:
        with open(dynamic_knowledge_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _save_dynamic_knowledge(entries: list):
    with open(dynamic_knowledge_file, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def _knowledge_list() -> list:
    if _turso_available():
        import turso_db
        return turso_db.list_entries()
    return _load_dynamic_knowledge()


def _knowledge_get(entry_id: int) -> Optional[dict]:
    if _turso_available():
        import turso_db
        return turso_db.get_entry(entry_id)
    entries = _load_dynamic_knowledge()
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    return None


def _knowledge_add(data: dict) -> tuple[dict, int]:
    if _turso_available():
        import turso_db
        new_entry = turso_db.add_entry(data)
        return new_entry, new_entry["id"]
    entries = _load_dynamic_knowledge()
    new_id = (max(e["id"] for e in entries) + 1) if entries else 1
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    new_entry = {
        "id": new_id,
        "titulo": data.get("titulo"),
        "categoria": data.get("categoria"),
        "conteudo": data.get("conteudo"),
        "tags": data.get("tags", []),
        "fonte": data.get("fonte", "api"),
        "data_criacao": timestamp,
        "status": "active",
    }
    entries.append(new_entry)
    _save_dynamic_knowledge(entries)
    return new_entry, new_id


def _knowledge_delete(entry_id: int) -> bool:
    if _turso_available():
        import turso_db
        return turso_db.delete_entry(entry_id)
    entries = _load_dynamic_knowledge()
    original_count = len(entries)
    entries = [e for e in entries if e.get("id") != entry_id]
    if len(entries) == original_count:
        return False
    _save_dynamic_knowledge(entries)
    return True


def _list_versions() -> list:
    versions = []
    if not os.path.isdir(versions_dir):
        return versions
    timestamp_pattern = re.compile(r'(\d{8}T\d{6})_')
    for fname in os.listdir(versions_dir):
        if fname.endswith(".md"):
            match = timestamp_pattern.search(fname)
            if match:
                topic = fname[:match.start()].rstrip('_')
                timestamp = match.group(1)
                version = fname[match.end():-3]
                versions.append({
                    "topic": topic,
                    "timestamp": timestamp,
                    "version": version,
                    "filename": fname,
                })
    versions.sort(key=lambda x: x["timestamp"], reverse=True)
    return versions


def _list_versions_for_topic(topic: str) -> list:
    return [v for v in _list_versions() if v["topic"] == topic]


def _products_endpoint() -> dict:
    counts = {}
    for product in _products:
        product_dir = os.path.join(_wiki_data_dir, product)
        if os.path.isdir(product_dir):
            md_files = [f for f in os.listdir(product_dir) if f.endswith(".md")]
            counts[product] = len(md_files)
        else:
            counts[product] = 0
    return {"products": _products, "counts": counts}


# ------------------------------------------------------------------
# Tool implementations
# ------------------------------------------------------------------

def tool_search(args: dict) -> str:
    query = args.get("query", "")
    product_filter = args.get("product", "")
    if not query:
        return json.dumps({"error": "Field 'query' is required"}, ensure_ascii=False)
    if product_filter and product_filter not in _products:
        return json.dumps({"error": f"Invalid product '{product_filter}'. Valid: {_products}"}, ensure_ascii=False)
    all_content = _load_all_markdown()
    results = _search_content(query, all_content, product_filter if product_filter else None)
    return json.dumps({
        "query": query,
        "product_filter": product_filter if product_filter else None,
        "count": len(results),
        "results": results,
    }, ensure_ascii=False)


def tool_topic(args: dict) -> str:
    topic = args.get("topic", "")
    if not topic:
        return json.dumps({"error": "Field 'topic' is required"}, ensure_ascii=False)
    path, product = _find_topic_file(topic)
    if path is None:
        return json.dumps({"error": f"Topic '{topic}' not found"}, ensure_ascii=False)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return json.dumps({
        "topic": topic,
        "product": product,
        "file": os.path.relpath(path, _wiki_data_dir),
        "content": content,
    }, ensure_ascii=False)


def tool_all_content(_args: dict) -> str:
    all_data = _load_all_markdown()
    result = {}
    for rel_path, data in all_data.items():
        result[rel_path] = {"content": data["content"], "product": data["product"]}
    return json.dumps({"count": len(result), "files": result}, ensure_ascii=False)


def tool_list_knowledge(_args: dict) -> str:
    entries = _knowledge_list()
    summary = []
    for entry in entries:
        summary.append({
            "id": entry.get("id"),
            "titulo": entry.get("titulo"),
            "categoria": entry.get("categoria"),
            "tags": entry.get("tags", []),
            "fonte": entry.get("fonte"),
            "data_criacao": entry.get("data_criacao"),
            "status": entry.get("status", "active"),
        })
    return json.dumps({"count": len(summary), "entries": summary}, ensure_ascii=False)


def tool_get_knowledge(args: dict) -> str:
    entry_id = args.get("entry_id")
    if entry_id is None:
        return json.dumps({"error": "Field 'entry_id' is required"}, ensure_ascii=False)
    try:
        entry_id = int(entry_id)
    except (ValueError, TypeError):
        return json.dumps({"error": "Field 'entry_id' must be an integer"}, ensure_ascii=False)
    entry = _knowledge_get(entry_id)
    if entry is None:
        return json.dumps({"error": f"Entry with ID {entry_id} not found"}, ensure_ascii=False)
    return json.dumps(entry, ensure_ascii=False)


def tool_add_knowledge(args: dict) -> str:
    titulo = args.get("titulo")
    categoria = args.get("categoria")
    conteudo = args.get("conteudo")
    if not titulo:
        return json.dumps({"error": "Field 'titulo' is required"}, ensure_ascii=False)
    if not categoria:
        return json.dumps({"error": "Field 'categoria' is required"}, ensure_ascii=False)
    if not conteudo:
        return json.dumps({"error": "Field 'conteudo' is required"}, ensure_ascii=False)
    new_entry, new_id = _knowledge_add(args)
    return json.dumps({"message": "Entry created successfully", "entry": new_entry}, ensure_ascii=False)


def tool_delete_knowledge(args: dict) -> str:
    entry_id = args.get("entry_id")
    if entry_id is None:
        return json.dumps({"error": "Field 'entry_id' is required"}, ensure_ascii=False)
    try:
        entry_id = int(entry_id)
    except (ValueError, TypeError):
        return json.dumps({"error": "Field 'entry_id' must be an integer"}, ensure_ascii=False)
    deleted = _knowledge_delete(entry_id)
    if not deleted:
        return json.dumps({"error": f"Entry with ID {entry_id} not found"}, ensure_ascii=False)
    return json.dumps({"message": f"Entry {entry_id} deleted successfully"}, ensure_ascii=False)


def tool_list_versions(_args: dict) -> str:
    all_versions = _list_versions()
    return json.dumps({"count": len(all_versions), "versions": all_versions}, ensure_ascii=False)


def tool_list_versions_topic(args: dict) -> str:
    topic = args.get("topic", "")
    if not topic:
        return json.dumps({"error": "Field 'topic' is required"}, ensure_ascii=False)
    topic_versions = _list_versions_for_topic(topic)
    return json.dumps({"topic": topic, "count": len(topic_versions), "versions": topic_versions}, ensure_ascii=False)


def tool_revert_topic(args: dict) -> str:
    topic = args.get("topic", "")
    version_id = args.get("version", "")
    if not topic:
        return json.dumps({"error": "Field 'topic' is required"}, ensure_ascii=False)
    if not version_id:
        return json.dumps({"error": "Field 'version' is required"}, ensure_ascii=False)
    path, product = _find_topic_file(topic)
    if path is None:
        return json.dumps({"error": f"Topic '{topic}' not found"}, ensure_ascii=False)
    matching = [v for v in _list_versions_for_topic(topic) if v["version"] == version_id]
    if not matching:
        return json.dumps({"error": f"No version '{version_id}' found for topic '{topic}'"}, ensure_ascii=False)
    version_to_restore = matching[0]
    backup_path = os.path.join(versions_dir, version_to_restore["filename"])
    if not os.path.exists(backup_path):
        return json.dumps({"error": f"Backup file not found: {version_to_restore['filename']}"}, ensure_ascii=False)
    with open(backup_path, "r", encoding="utf-8") as f:
        backup_content = f.read()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            current_content = f.read()
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        pre_backup_filename = f"{topic}_{timestamp}_pre_revert.md"
        with open(os.path.join(versions_dir, pre_backup_filename), "w", encoding="utf-8") as f:
            f.write(current_content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(backup_content)
    return json.dumps({
        "message": "Topic reverted successfully",
        "topic": topic,
        "product": product,
        "file": os.path.relpath(path, _wiki_data_dir),
        "restored_from": version_to_restore["filename"],
        "restored_timestamp": version_to_restore["timestamp"],
        "restored_version": version_to_restore["version"],
    }, ensure_ascii=False)


def tool_products(_args: dict) -> str:
    return json.dumps(_products_endpoint(), ensure_ascii=False)


# ------------------------------------------------------------------
# Tool registry
# ------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "search",
        "description": "Pesquisa palavra-chave em todos os documentos da base de conhecimento. Pode filtrar por produto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Palavra ou expressão a pesquisar"},
                "product": {
                    "type": "string",
                    "description": "Filtro opcional por produto (olx / standvirtual / imovirtual / transversal)",
                    "enum": ["olx", "standvirtual", "imovirtual", "transversal"],
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "topic",
        "description": "Devolve o conteúdo completo de um tópico específico da base de conhecimento.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Nome do tópico (slug do ficheiro .md, ex: 'pacotes', 'reembolso', 'verificar-controlauto')",
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "all_content",
        "description": "Devolve todo o conteúdo da base de conhecimento — todos os ficheiros markdown.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_knowledge",
        "description": "Lista todas as entradas de conhecimento dinâmico (id, título, categoria, data, estado). Sem conteúdo completo.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_knowledge",
        "description": "Devolve uma entrada específica de conhecimento dinâmico, com o conteúdo completo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "integer", "description": "ID da entrada de conhecimento"},
            },
            "required": ["entry_id"],
        },
    },
    {
        "name": "add_knowledge",
        "description": "Adiciona uma nova entrada de conhecimento dinâmico à base de dados.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título curto da entrada"},
                "categoria": {"type": "string", "description": "Categoria (ex: casos, procedimentos, faq, templates)"},
                "conteudo": {"type": "string", "description": "Conteúdo completo em texto ou markdown"},
                "tags": {"type": "string", "description": "Etiquetas separadas por vírgulas (opcional)"},
                "fonte": {"type": "string", "description": "Origem da informação (opcional)"},
            },
            "required": ["titulo", "categoria", "conteudo"],
        },
    },
    {
        "name": "delete_knowledge",
        "description": "Remove uma entrada de conhecimento dinâmico pelo ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "integer", "description": "ID da entrada a remover"},
            },
            "required": ["entry_id"],
        },
    },
    {
        "name": "list_versions",
        "description": "Lista todas as versões guardadas de todos os tópicos (mais recente primeiro).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_versions_topic",
        "description": "Lista as versões guardadas de um tópico específico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Nome do tópico"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "revert_topic",
        "description": "Reverte um tópico para uma versão anterior guardada.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Nome do tópico a reverter"},
                "version": {"type": "string", "description": "Identificador da versão a restaurar (retornado por list_versions_topic)"},
            },
            "required": ["topic", "version"],
        },
    },
    {
        "name": "products",
        "description": "Lista as 4 categorias de produto (OLX, Standvirtual, Imovirtual, Transversal) com a contagem de páginas em cada uma.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

TOOL_FUNCTIONS: dict[str, callable] = {
    "search": tool_search,
    "topic": tool_topic,
    "all_content": tool_all_content,
    "list_knowledge": tool_list_knowledge,
    "get_knowledge": tool_get_knowledge,
    "add_knowledge": tool_add_knowledge,
    "delete_knowledge": tool_delete_knowledge,
    "list_versions": tool_list_versions,
    "list_versions_topic": tool_list_versions_topic,
    "revert_topic": tool_revert_topic,
    "products": tool_products,
}


# ------------------------------------------------------------------
# Resource helpers
# ------------------------------------------------------------------

def list_resources() -> list[dict]:
    """Build the resources list from wiki_data/ files."""
    resources = []
    for product in _products:
        product_dir = os.path.join(_wiki_data_dir, product)
        if os.path.isdir(product_dir):
            for fname in os.listdir(product_dir):
                if fname.endswith(".md"):
                    uri = f"wiki://{product}/{fname[:-3]}"
                    slug = fname[:-3]
                    resources.append({
                        "uri": uri,
                        "name": f"{product.title()} / {slug}",
                        "mimeType": "text/markdown",
                        "description": f"Ficheiro wiki: {product}/{fname}",
                    })
    return resources


def read_resource(uri: str) -> str:
    """Read content from a wiki:// URI."""
    # Format: wiki://product/filename (without .md)
    if not uri.startswith("wiki://"):
        raise ValueError(f"Unknown URI scheme: {uri}")
    remainder = uri[len("wiki://"):]
    parts = remainder.split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"Invalid wiki URI: {uri} — expected wiki://product/filename")
    product = parts[0]
    slug = parts[1]
    product_dir = os.path.join(_wiki_data_dir, product)
    filepath = os.path.join(product_dir, f"{slug}.md")
    if not os.path.exists(filepath):
        raise ValueError(f"Resource not found: {uri}")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------
# MCP JSON-RPC handler
# ------------------------------------------------------------------

def handle_mcp_request(request_data: dict) -> dict:
    """
    Process a single MCP JSON-RPC 2.0 request and return a JSON-RPC 2.0 response.
    Supports: initialize, ping, tools/list, tools/call, resources/list, resources/read.
    """
    jsonrpc = request_data.get("jsonrpc", "2.0")
    req_id = request_data.get("id")
    method = request_data.get("method", "")

    # --- initialize ---
    if method == "initialize":
        params = request_data.get("params", {})
        return {
            "jsonrpc": jsonrpc,
            "id": req_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                },
                "serverInfo": {
                    "name": "onecs-kb-api",
                    "version": "1.0.0",
                },
            },
        }

    # --- ping ---
    if method == "ping":
        return {
            "jsonrpc": jsonrpc,
            "id": req_id,
            "result": {},
        }

    # --- tools/list ---
    if method == "tools/list":
        return {
            "jsonrpc": jsonrpc,
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    # --- tools/call ---
    if method == "tools/call":
        params = request_data.get("params", {})
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if not tool_name:
            return _error_response(jsonrpc, req_id, -32602, "Missing 'name' in tools/call")
        if tool_name not in TOOL_FUNCTIONS:
            return _error_response(jsonrpc, req_id, -32602, f"Unknown tool: {tool_name}")

        try:
            raw_result = TOOL_FUNCTIONS[tool_name](tool_args)
            result_obj = json.loads(raw_result)
            if "error" in result_obj:
                return _error_response(jsonrpc, req_id, -32602, result_obj["error"])
            return {
                "jsonrpc": jsonrpc,
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": raw_result,
                        }
                    ]
                },
            }
        except Exception as exc:
            return _error_response(jsonrpc, req_id, -32603, str(exc))

    # --- resources/list ---
    if method == "resources/list":
        return {
            "jsonrpc": jsonrpc,
            "id": req_id,
            "result": {"resources": list_resources()},
        }

    # --- resources/read ---
    if method == "resources/read":
        params = request_data.get("params", {})
        uri = params.get("uri", "")
        if not uri:
            return _error_response(jsonrpc, req_id, -32602, "Missing 'uri' in resources/read")
        try:
            content = read_resource(uri)
            return {
                "jsonrpc": jsonrpc,
                "id": req_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/markdown",
                            "text": content,
                        }
                    ]
                },
            }
        except Exception as exc:
            return _error_response(jsonrpc, req_id, -32603, str(exc))

    # --- unknown method ---
    return _error_response(jsonrpc, req_id, -32601, f"Method not found: {method}")


def _error_response(jsonrpc: str, req_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": jsonrpc,
        "id": req_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
