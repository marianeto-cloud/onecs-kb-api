"""
MCP Server for OneCs KB API
============================
Implements the Model Context Protocol (MCP) JSON-RPC 2.0 over HTTP.
Streamable HTTP transport — no external MCP package dependencies (mantido
assim de propósito, para compatibilidade com o cliente MCP do Toqan/
ToqanClaw, que fala diretamente JSON-RPC 2.0 sem exigir o handshake da
SDK oficial nem autenticação por API key própria — a autenticação é feita
nas Connections do agente).

Toda a lógica de negócio (pesquisa, tópicos, conhecimento dinâmico,
versionamento) vive em kb_core.py e é PARTILHADA com o app.py (REST) —
este ficheiro trata apenas do "transporte" JSON-RPC.

Suporta:
  - initialize     (handshake)
  - ping           (keep-alive)
  - tools/list     (enumerate available tools)
  - tools/call     (invoke a named tool with arguments)
  - resources/list (enumerate wiki files as resources)
  - resources/read (fetch a specific resource URI)
"""

from __future__ import annotations

import json
import os
from typing import Any

import kb_core

PRODUCTS = ["olx", "standvirtual", "imovirtual", "transversal"]


def init_mcp():
    """Mantido por compatibilidade com app.py (agora é um no-op — a
    configuração real é feita uma única vez em kb_core.init(), chamado
    pelo app.py antes deste)."""
    pass


# ------------------------------------------------------------------
# Tool implementations — todas delegam para kb_core.py
# ------------------------------------------------------------------

def tool_search(args: dict) -> str:
    query = args.get("query", "")
    product_filter = args.get("product", "")
    if not query:
        return json.dumps({"error": "Field 'query' is required"}, ensure_ascii=False)
    if product_filter and product_filter not in PRODUCTS:
        return json.dumps({"error": f"Invalid product '{product_filter}'. Valid: {PRODUCTS}"}, ensure_ascii=False)

    results = kb_core.search_content(query, product_filter if product_filter else None)
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

    content, product, rel_path = kb_core.get_topic_content(topic)
    if content is None:
        return json.dumps({"error": f"Topic '{topic}' not found"}, ensure_ascii=False)

    return json.dumps({
        "topic": topic,
        "product": product,
        "file": rel_path,
        "content": content,
    }, ensure_ascii=False)


def tool_all_content(_args: dict) -> str:
    all_data = kb_core.load_all_markdown()
    return json.dumps({"count": len(all_data), "files": all_data}, ensure_ascii=False)


def tool_list_knowledge(_args: dict) -> str:
    entries = kb_core.knowledge_list()
    return json.dumps({"count": len(entries), "entries": entries}, ensure_ascii=False)


def tool_get_knowledge(args: dict) -> str:
    entry_id = args.get("entry_id")
    if entry_id is None:
        return json.dumps({"error": "Field 'entry_id' is required"}, ensure_ascii=False)
    try:
        entry_id = int(entry_id)
    except (ValueError, TypeError):
        return json.dumps({"error": "Field 'entry_id' must be an integer"}, ensure_ascii=False)

    entry = kb_core.knowledge_get(entry_id)
    if entry is None:
        return json.dumps({"error": f"Entry with ID {entry_id} not found"}, ensure_ascii=False)
    return json.dumps(entry, ensure_ascii=False)


def tool_add_knowledge(args: dict) -> str:
    if not args.get("titulo"):
        return json.dumps({"error": "Field 'titulo' is required"}, ensure_ascii=False)
    if not args.get("categoria"):
        return json.dumps({"error": "Field 'categoria' is required"}, ensure_ascii=False)
    if not args.get("conteudo"):
        return json.dumps({"error": "Field 'conteudo' is required"}, ensure_ascii=False)

    new_entry = kb_core.knowledge_add(args)
    return json.dumps({"message": "Entry created successfully", "entry": new_entry}, ensure_ascii=False)


def tool_delete_knowledge(args: dict) -> str:
    entry_id = args.get("entry_id")
    if entry_id is None:
        return json.dumps({"error": "Field 'entry_id' is required"}, ensure_ascii=False)
    try:
        entry_id = int(entry_id)
    except (ValueError, TypeError):
        return json.dumps({"error": "Field 'entry_id' must be an integer"}, ensure_ascii=False)

    deleted = kb_core.knowledge_delete(entry_id)
    if not deleted:
        return json.dumps({"error": f"Entry with ID {entry_id} not found"}, ensure_ascii=False)
    return json.dumps({"message": f"Entry {entry_id} deleted successfully"}, ensure_ascii=False)


def tool_list_versions(_args: dict) -> str:
    versions = kb_core.list_versions()
    return json.dumps({"count": len(versions), "versions": versions}, ensure_ascii=False)


def tool_list_versions_topic(args: dict) -> str:
    topic = args.get("topic", "")
    if not topic:
        return json.dumps({"error": "Field 'topic' is required"}, ensure_ascii=False)
    versions = kb_core.list_versions_for_topic(topic)
    return json.dumps({"topic": topic, "count": len(versions), "versions": versions}, ensure_ascii=False)


def tool_revert_topic(args: dict) -> str:
    topic = args.get("topic", "")
    version_id = args.get("version", "")
    if not topic:
        return json.dumps({"error": "Field 'topic' is required"}, ensure_ascii=False)
    if not version_id:
        return json.dumps({"error": "Field 'version' is required"}, ensure_ascii=False)

    result = kb_core.revert_topic(topic, version_id)
    return json.dumps(result, ensure_ascii=False)


def tool_products(_args: dict) -> str:
    return json.dumps(kb_core.products_summary(), ensure_ascii=False)


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
                    "enum": PRODUCTS,
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
    """Build the resources list from wiki_data/ files (via kb_core)."""
    resources = []
    all_data = kb_core.load_all_markdown()
    for rel_path, data in all_data.items():
        product = data["product"]
        fname = os.path.basename(rel_path)
        slug = fname[:-3] if fname.endswith(".md") else fname
        uri = f"wiki://{product}/{slug}"
        resources.append({
            "uri": uri,
            "name": f"{product.title()} / {slug}",
            "mimeType": "text/markdown",
            "description": f"Ficheiro wiki: {rel_path}",
        })
    return resources


def read_resource(uri: str) -> str:
    """Read content from a wiki:// URI (via kb_core, incluindo overrides)."""
    if not uri.startswith("wiki://"):
        raise ValueError(f"Unknown URI scheme: {uri}")
    remainder = uri[len("wiki://"):]
    parts = remainder.split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"Invalid wiki URI: {uri} — expected wiki://product/filename")
    slug = parts[1]
    content, _, _ = kb_core.get_topic_content(slug)
    if content is None:
        raise ValueError(f"Resource not found: {uri}")
    return content


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

    if method == "initialize":
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
                    "version": "2.0.0",
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": jsonrpc, "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": jsonrpc, "id": req_id, "result": {"tools": TOOLS}}

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
                    "content": [{"type": "text", "text": raw_result}],
                },
            }
        except Exception as exc:
            return _error_response(jsonrpc, req_id, -32603, str(exc))

    if method == "resources/list":
        return {"jsonrpc": jsonrpc, "id": req_id, "result": {"resources": list_resources()}}

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
                    "contents": [{"uri": uri, "mimeType": "text/markdown", "text": content}],
                },
            }
        except Exception as exc:
            return _error_response(jsonrpc, req_id, -32603, str(exc))

    return _error_response(jsonrpc, req_id, -32601, f"Method not found: {method}")


def _error_response(jsonrpc: str, req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": jsonrpc, "id": req_id, "error": {"code": code, "message": message}}
