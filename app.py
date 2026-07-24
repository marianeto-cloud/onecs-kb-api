import os
from flask import Flask, request, jsonify
from flask_cors import CORS

import kb_core
import mcp_server

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(__file__)
WIKI_DATA_DIR = os.path.join(BASE_DIR, "wiki_data")
VERSIONS_DIR = os.path.join(BASE_DIR, "versions")
DYNAMIC_KNOWLEDGE_FILE = os.path.join(BASE_DIR, "dynamic_knowledge.json")

PRODUCTS = ["olx", "standvirtual", "imovirtual", "transversal"]

# ------------------------------------------------------------------
# Startup: injeta a configuração no módulo partilhado kb_core, que trata
# de inicializar a Turso (se configurada) e migrar o dynamic_knowledge.json
# ------------------------------------------------------------------
kb_core.init(BASE_DIR, WIKI_DATA_DIR, VERSIONS_DIR, DYNAMIC_KNOWLEDGE_FILE, PRODUCTS)
mcp_server.init_mcp()


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
@app.route("/")
def root():
    return jsonify({
        "name": "OneCs Knowledge Base API",
        "version": "2.0.0",
        "description": "Serves the OneCs/OLX team knowledge base for OLX, Standvirtual, Imovirtual, and transversal content",
        "products": PRODUCTS,
        "storage": "turso" if kb_core.turso_available() else "json/local-files",
        "endpoints": {
            "GET /": "API info and available endpoints",
            "GET /health": "Health check endpoint",
            "GET /products": "List the 4 product categories with page counts",
            "GET /search?q=<query>&product=<product>": "Search across wiki pages (optional product filter)",
            "GET /topic/<topic>": "Return full content of a specific topic",
            "PUT /topic/<topic>": "Replace a topic's content with versioning",
            "GET /all": "Return all wiki content as JSON keyed by file path",
            "GET /knowledge": "List all dynamic knowledge entries (summary)",
            "GET /knowledge/<id>": "Return full content of a specific dynamic knowledge entry",
            "POST /knowledge": "Add a new dynamic knowledge entry",
            "DELETE /knowledge/<id>": "Delete a dynamic knowledge entry by ID",
            "GET /versions": "List all saved versions across all topics",
            "GET /versions/<topic>": "List versions for a specific topic",
            "POST /revert/<topic>": "Revert a topic to a previous version",
            "POST /mcp": "MCP JSON-RPC 2.0 endpoint for AI agents",
            "GET /mcp": "MCP capability summary / SSE keep-alive",
        },
    })


@app.route("/health")
def health():
    return jsonify({"status": "OK"})


@app.route("/products")
def products():
    return jsonify(kb_core.products_summary())


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Missing query parameter 'q'"}), 400
    product_filter = request.args.get("product", "").strip().lower()
    if product_filter and product_filter not in PRODUCTS:
        return jsonify({"error": f"Invalid product '{product_filter}'. Valid products: {PRODUCTS}"}), 400

    results = kb_core.search_content(q, product_filter if product_filter else None)
    return jsonify({
        "query": q,
        "product_filter": product_filter if product_filter else None,
        "count": len(results),
        "results": results,
    })


@app.route("/topic/<topic>")
def topic_get(topic):
    content, product, rel_path = kb_core.get_topic_content(topic)
    if content is None:
        return jsonify({"error": f"Topic '{topic}' not found"}), 404
    return jsonify({
        "topic": topic,
        "product": product,
        "file": rel_path,
        "content": content,
    })


@app.route("/topic/<topic>", methods=["PUT"])
def topic_update(topic):
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    conteudo = data.get("conteudo")
    if not conteudo:
        return jsonify({"error": "Field 'conteudo' is required"}), 400

    result = kb_core.update_topic(topic, conteudo, versao=data.get("versao"), nota=data.get("nota"))
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route("/all")
def all_content():
    all_data = kb_core.load_all_markdown()
    return jsonify({"count": len(all_data), "files": all_data})


@app.route("/knowledge")
def knowledge_list():
    entries = kb_core.knowledge_list()
    return jsonify({"count": len(entries), "entries": entries})


@app.route("/knowledge/<int:entry_id>")
def knowledge_get(entry_id):
    entry = kb_core.knowledge_get(entry_id)
    if entry is None:
        return jsonify({"error": f"Entry with ID {entry_id} not found"}), 404
    return jsonify(entry)


@app.route("/knowledge", methods=["POST"])
def knowledge_add():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    if not data.get("titulo"):
        return jsonify({"error": "Field 'titulo' is required"}), 400
    if not data.get("categoria"):
        return jsonify({"error": "Field 'categoria' is required"}), 400
    if not data.get("conteudo"):
        return jsonify({"error": "Field 'conteudo' is required"}), 400

    new_entry = kb_core.knowledge_add(data)
    return jsonify({"message": "Entry created successfully", "entry": new_entry}), 201


@app.route("/knowledge/<int:entry_id>", methods=["DELETE"])
def knowledge_delete(entry_id):
    deleted = kb_core.knowledge_delete(entry_id)
    if not deleted:
        return jsonify({"error": f"Entry with ID {entry_id} not found"}), 404
    return jsonify({"message": f"Entry {entry_id} deleted successfully"})


@app.route("/versions")
def versions_list():
    versions = kb_core.list_versions()
    return jsonify({"count": len(versions), "versions": versions})


@app.route("/versions/<topic>")
def versions_for_topic(topic):
    versions = kb_core.list_versions_for_topic(topic)
    return jsonify({"topic": topic, "count": len(versions), "versions": versions})


@app.route("/revert/<topic>", methods=["POST"])
def topic_revert(topic):
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    version_id = data.get("versao")
    if not version_id:
        return jsonify({"error": "Field 'versao' is required"}), 400

    result = kb_core.revert_topic(topic, version_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


# ------------------------------------------------------------------
# MCP endpoint (Model Context Protocol) — JSON-RPC 2.0 sobre HTTP
# ------------------------------------------------------------------
@app.route("/mcp", methods=["POST"])
def mcp_post():
    if not request.is_json:
        return jsonify({
            "jsonrpc": "2.0", "id": None,
            "error": {"code": -32700, "message": "Content-Type must be application/json"},
        }), 400

    request_data = request.get_json()
    response_data = mcp_server.handle_mcp_request(request_data)
    resp = jsonify(response_data)
    resp.headers["MCP-Protocol-Version"] = "2025-03-26"
    return resp


@app.route("/mcp", methods=["GET"])
def mcp_get():
    accept = request.headers.get("Accept", "")
    if "text/event-stream" in accept:
        from flask import Response
        import json
        import time
        from datetime import datetime, timezone

        def event_stream():
            while True:
                msg = "data: " + json.dumps({
                    "event": "ping",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }) + chr(10) + chr(10)
                yield msg
                time.sleep(30)

        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={"MCP-Protocol-Version": "2025-03-26"},
        )

    return jsonify({
        "name": "onecs-kb-api",
        "version": "2.0.0",
        "mcp_protocol_version": "2025-03-26",
        "mcp_endpoint": "/mcp",
        "capabilities": {
            "tools": {"list": True, "call": True},
            "resources": {"list": True, "read": True},
        },
        "tools_available": len(mcp_server.TOOLS),
        "resources_available": len(mcp_server.list_resources()),
    })


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
