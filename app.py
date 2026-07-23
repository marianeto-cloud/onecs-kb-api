import os
import re
import json
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

import turso_db
import mcp_server

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(__file__)
WIKI_DATA_DIR = os.path.join(BASE_DIR, "wiki_data")
VERSIONS_DIR = os.path.join(BASE_DIR, "versions")
DYNAMIC_KNOWLEDGE_FILE = os.path.join(BASE_DIR, "dynamic_knowledge.json")

PRODUCTS = ["olx", "standvirtual", "imovirtual", "transversal"]

# ------------------------------------------------------------------
# Startup: initialise Turso DB and migrate from JSON if needed
# ------------------------------------------------------------------

def _turso_available():
    return bool(os.environ.get("TURSO_DATABASE_URL", "")) and bool(
        os.environ.get("TURSO_AUTH_TOKEN", "")
    )


if _turso_available():
    try:
        turso_db.init_db()
        turso_db.migrate_from_json(DYNAMIC_KNOWLEDGE_FILE)
    except Exception as e:
        print(f"[WARN] Turso init/migrate failed: {e}")

    # Initialise MCP server with app paths (always, regardless of Turso availability)
mcp_server.init_mcp(BASE_DIR, WIKI_DATA_DIR, VERSIONS_DIR, DYNAMIC_KNOWLEDGE_FILE, PRODUCTS)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def get_all_files_with_product():
    """Return all markdown files with their product category."""
    files = []
    for product in PRODUCTS:
        product_dir = os.path.join(WIKI_DATA_DIR, product)
        if os.path.isdir(product_dir):
            for fname in os.listdir(product_dir):
                if fname.endswith(".md"):
                    files.append({
                        "relative_path": os.path.join(product, fname),
                        "product": product,
                        "full_path": os.path.join(product_dir, fname)
                    })
    return files


def load_all_markdown():
    """Load all wiki markdown files keyed by relative path with product info."""
    all_content = {}
    for product in PRODUCTS:
        product_dir = os.path.join(WIKI_DATA_DIR, product)
        if os.path.isdir(product_dir):
            for fname in os.listdir(product_dir):
                if fname.endswith(".md"):
                    rel = os.path.join(product, fname)
                    full_path = os.path.join(product_dir, fname)
                    with open(full_path, "r", encoding="utf-8") as f:
                        all_content[rel] = {
                            "content": f.read(),
                            "product": product
                        }
    return all_content


def find_topic_file(topic):
    """Find the file for a given topic across all product directories."""
    for product in PRODUCTS:
        product_dir = os.path.join(WIKI_DATA_DIR, product)
        if os.path.isdir(product_dir):
            # Try exact match
            path = os.path.join(product_dir, f"{topic}.md")
            if os.path.exists(path):
                return path, product
            # Try case-insensitive match
            for fname in os.listdir(product_dir):
                if fname.lower() == f"{topic}.md".lower():
                    return os.path.join(product_dir, fname), product
    return None, None


def search_content(query, all_content, product_filter=None):
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
                    "snippet": snippet.strip()
                })
    return results


# ------------------------------------------------------------------
# JSON fallback helpers (used when Turso is not configured)
# ------------------------------------------------------------------

def load_dynamic_knowledge():
    """Load dynamic knowledge entries from JSON file."""
    if not os.path.exists(DYNAMIC_KNOWLEDGE_FILE):
        return []
    try:
        with open(DYNAMIC_KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, IOError):
        return []


def save_dynamic_knowledge(entries):
    """Save dynamic knowledge entries to JSON file."""
    with open(DYNAMIC_KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def get_next_id_json(entries):
    """Get the next available ID for a new entry (JSON mode)."""
    if not entries:
        return 1
    return max(entry["id"] for entry in entries) + 1


# ------------------------------------------------------------------
# Knowledge helpers (use Turso when available, JSON fallback otherwise)
# ------------------------------------------------------------------

def _knowledge_list():
    """List all knowledge entries (summary, no full content)."""
    if _turso_available():
        return turso_db.list_entries()
    return load_dynamic_knowledge()


def _knowledge_get(entry_id):
    """Get a single knowledge entry by ID."""
    if _turso_available():
        return turso_db.get_entry(entry_id)
    entries = load_dynamic_knowledge()
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    return None


def _knowledge_add(data):
    """Add a new knowledge entry. Returns (new_entry, next_id)."""
    if _turso_available():
        new_entry = turso_db.add_entry(data)
        return new_entry, new_entry["id"]
    entries = load_dynamic_knowledge()
    new_id = get_next_id_json(entries)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    new_entry = {
        "id": new_id,
        "titulo": data.get("titulo"),
        "categoria": data.get("categoria"),
        "conteudo": data.get("conteudo"),
        "tags": data.get("tags", []),
        "fonte": data.get("fonte", "api"),
        "data_criacao": timestamp,
        "status": "active"
    }
    entries.append(new_entry)
    save_dynamic_knowledge(entries)
    return new_entry, new_id


def _knowledge_delete(entry_id):
    """Delete a knowledge entry by ID. Returns True if deleted."""
    if _turso_available():
        return turso_db.delete_entry(entry_id)
    entries = load_dynamic_knowledge()
    original_count = len(entries)
    entries = [e for e in entries if e.get("id") != entry_id]
    if len(entries) == original_count:
        return False
    save_dynamic_knowledge(entries)
    return True


# ------------------------------------------------------------------
# Version helpers
# ------------------------------------------------------------------

def list_versions():
    """List all saved versions across all topics."""
    versions = []
    if not os.path.isdir(VERSIONS_DIR):
        return versions

    # Timestamp pattern: YYYYMMDDTHHMMSS_ (search anywhere in filename)
    timestamp_pattern = re.compile(r'(\d{8}T\d{6})_')

    for fname in os.listdir(VERSIONS_DIR):
        if fname.endswith(".md"):
            # Filename format: topic_timestamp_version.md
            # Find the timestamp to split topic from timestamp+version
            match = timestamp_pattern.search(fname)
            if match:
                # Topic is everything before the timestamp (minus trailing underscore)
                topic = fname[:match.start()].rstrip('_')
                timestamp = match.group(1)
                # Version is everything after timestamp_ up to .md
                version_start = match.end()
                version = fname[version_start:-3]  # -3 to remove .md

                versions.append({
                    "topic": topic,
                    "timestamp": timestamp,
                    "version": version,
                    "filename": fname
                })
    # Sort by timestamp descending (newest first)
    versions.sort(key=lambda x: x["timestamp"], reverse=True)
    return versions


def list_versions_for_topic(topic):
    """List versions for a specific topic."""
    all_versions = list_versions()
    return [v for v in all_versions if v["topic"] == topic]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.route("/")
def root():
    return jsonify({
        "name": "OneCs Knowledge Base API",
        "version": "1.0.0",
        "description": "Serves the OneCs/OLX team knowledge base for OLX, Standvirtual, Imovirtual, and transversal content",
        "products": PRODUCTS,
        "storage": "turso" if _turso_available() else "json",
        "endpoints": {
            "GET /": "API info and available endpoints",
            "GET /products": "List the 4 product categories with page counts",
            "GET /search?q=<query>&product=<product>": "Search across wiki pages (optional product filter)",
            "GET /topic/<topic>": "Return full content of a specific topic",
            "GET /all": "Return all wiki content as JSON keyed by file path",
            "GET /knowledge": "List all dynamic knowledge entries (summary)",
            "GET /knowledge/<id>": "Return full content of a specific dynamic knowledge entry",
            "POST /knowledge": "Add a new dynamic knowledge entry",
            "DELETE /knowledge/<id>": "Delete a dynamic knowledge entry by ID",
            "GET /versions": "List all saved versions across all topics",
            "GET /versions/<topic>": "List versions for a specific topic",
            "PUT /topic/<topic>": "Replace a topic's content with versioning",
            "POST /revert/<topic>": "Revert a topic to a previous version",
            "GET /health": "Health check endpoint"
        }
    })


@app.route("/health")
def health():
    return jsonify({"status": "OK"})


@app.route("/products")
def products():
    """List the 4 product categories with page counts."""
    counts = {}
    for product in PRODUCTS:
        product_dir = os.path.join(WIKI_DATA_DIR, product)
        if os.path.isdir(product_dir):
            md_files = [f for f in os.listdir(product_dir) if f.endswith(".md")]
            counts[product] = len(md_files)
        else:
            counts[product] = 0
    return jsonify({
        "products": PRODUCTS,
        "counts": counts
    })


@app.route("/search")
def search():
    """Search across wiki pages with optional product filter."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Missing query parameter 'q'"}), 400
    product_filter = request.args.get("product", "").strip().lower()
    if product_filter and product_filter not in PRODUCTS:
        return jsonify({"error": f"Invalid product '{product_filter}'. Valid products: {PRODUCTS}"}), 400

    all_content = load_all_markdown()
    results = search_content(q, all_content, product_filter if product_filter else None)
    return jsonify({
        "query": q,
        "product_filter": product_filter if product_filter else None,
        "count": len(results),
        "results": results
    })


@app.route("/topic/<topic>")
def topic(topic):
    """Return full content of a specific topic."""
    path, product = find_topic_file(topic)
    if path is None:
        return jsonify({"error": f"Topic '{topic}' not found"}), 404
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({
            "topic": topic,
            "product": product,
            "file": os.path.relpath(path, WIKI_DATA_DIR),
            "content": content
        })
    except IOError as e:
        return jsonify({"error": f"Error reading topic: {str(e)}"}), 500


@app.route("/all")
def all_content():
    """Return all wiki content as JSON keyed by file path."""
    all_data = load_all_markdown()
    result = {}
    for rel_path, data in all_data.items():
        result[rel_path] = {
            "content": data["content"],
            "product": data["product"]
        }
    return jsonify({
        "count": len(result),
        "files": result
    })


@app.route("/knowledge")
def knowledge_list():
    """List all dynamic knowledge entries (summary, no full content)."""
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
            "status": entry.get("status", "active")
        })
    return jsonify({
        "count": len(summary),
        "entries": summary
    })


@app.route("/knowledge/<int:entry_id>")
def knowledge_get(entry_id):
    """Return full content of a specific dynamic knowledge entry."""
    entry = _knowledge_get(entry_id)
    if entry is None:
        return jsonify({"error": f"Entry with ID {entry_id} not found"}), 404
    return jsonify(entry)


@app.route("/knowledge", methods=["POST"])
def knowledge_add():
    """Add a new dynamic knowledge entry."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    titulo = data.get("titulo")
    categoria = data.get("categoria")
    conteudo = data.get("conteudo")

    if not titulo:
        return jsonify({"error": "Field 'titulo' is required"}), 400
    if not categoria:
        return jsonify({"error": "Field 'categoria' is required"}), 400
    if not conteudo:
        return jsonify({"error": "Field 'conteudo' is required"}), 400

    new_entry, _ = _knowledge_add(data)

    return jsonify({
        "message": "Entry created successfully",
        "entry": new_entry
    }), 201


@app.route("/knowledge/<int:entry_id>", methods=["DELETE"])
def knowledge_delete(entry_id):
    """Delete a dynamic knowledge entry by ID."""
    deleted = _knowledge_delete(entry_id)
    if not deleted:
        return jsonify({"error": f"Entry with ID {entry_id} not found"}), 404
    return jsonify({"message": f"Entry {entry_id} deleted successfully"})


@app.route("/versions")
def versions_list():
    """List all saved versions across all topics."""
    all_versions = list_versions()
    return jsonify({
        "count": len(all_versions),
        "versions": all_versions
    })


@app.route("/versions/<topic>")
def versions_for_topic(topic):
    """List versions for a specific topic."""
    topic_versions = list_versions_for_topic(topic)
    return jsonify({
        "topic": topic,
        "count": len(topic_versions),
        "versions": topic_versions
    })


@app.route("/topic/<topic>", methods=["PUT"])
def topic_update(topic):
    """Replace a topic's content with versioning."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    conteudo = data.get("conteudo")

    if not conteudo:
        return jsonify({"error": "Field 'conteudo' is required"}), 400

    path, product = find_topic_file(topic)
    if path is None:
        return jsonify({"error": f"Topic '{topic}' not found"}), 404

    # Read current content (for backup)
    current_content = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            current_content = f.read()

    # Create backup
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    version_id = data.get("versao", timestamp)
    backup_filename = f"{topic}_{timestamp}_{version_id}.md"
    backup_path = os.path.join(VERSIONS_DIR, backup_filename)

    if current_content:
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(current_content)

    # Write new content
    with open(path, "w", encoding="utf-8") as f:
        f.write(conteudo)

    return jsonify({
        "message": "Topic updated successfully",
        "topic": topic,
        "product": product,
        "file": os.path.relpath(path, WIKI_DATA_DIR),
        "backup": backup_filename,
        "version": version_id,
        "note": data.get("nota")
    })


@app.route("/revert/<topic>", methods=["POST"])
def topic_revert(topic):
    """Revert a topic to a previous version."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json()
    version_id = data.get("versao")

    if not version_id:
        return jsonify({"error": "Field 'versao' is required"}), 400

    path, product = find_topic_file(topic)
    if path is None:
        return jsonify({"error": f"Topic '{topic}' not found"}), 404

    # Find the most recent backup matching topic+version
    all_versions = list_versions_for_topic(topic)
    matching = [v for v in all_versions if v["version"] == version_id]

    if not matching:
        return jsonify({"error": f"No version '{version_id}' found for topic '{topic}'"}), 404

    # Use the most recent matching version
    version_to_restore = matching[0]
    backup_path = os.path.join(VERSIONS_DIR, version_to_restore["filename"])

    if not os.path.exists(backup_path):
        return jsonify({"error": f"Backup file not found: {version_to_restore['filename']}"}), 500

    # Read backup content
    with open(backup_path, "r", encoding="utf-8") as f:
        backup_content = f.read()

    # Save current as new backup before reverting
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            current_content = f.read()
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        pre_backup_filename = f"{topic}_{timestamp}_pre_revert.md"
        with open(os.path.join(VERSIONS_DIR, pre_backup_filename), "w", encoding="utf-8") as f:
            f.write(current_content)

    # Write restored content
    with open(path, "w", encoding="utf-8") as f:
        f.write(backup_content)

    return jsonify({
        "message": "Topic reverted successfully",
        "topic": topic,
        "product": product,
        "file": os.path.relpath(path, WIKI_DATA_DIR),
        "restored_from": version_to_restore["filename"],
        "restored_timestamp": version_to_restore["timestamp"],
        "restored_version": version_to_restore["version"]
    })



# ------------------------------------------------------------------
# MCP endpoint (Model Context Protocol)
# ------------------------------------------------------------------

@app.route("/mcp", methods=["POST"])
def mcp_post():
    """Handle MCP JSON-RPC 2.0 POST requests."""
    if not request.is_json:
        return jsonify({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Content-Type must be application/json"}}), 400

    request_data = request.get_json()
    response_data = mcp_server.handle_mcp_request(request_data)
    resp = jsonify(response_data)
    resp.headers["MCP-Protocol-Version"] = "2025-03-26"
    return resp


@app.route("/mcp", methods=["GET"])
def mcp_get():
    """Handle MCP GET requests (SSE / Server-Sent Events)."""
    accept = request.headers.get("Accept", "")
    if "text/event-stream" in accept:
        # SSE: send a simple ping to keep the connection alive
        from flask import Response
        def event_stream():
            import time
            while True:
                msg = "data: " + json.dumps({"event": "ping", "timestamp": datetime.utcnow().isoformat()}) + chr(10) + chr(10)
                yield msg
                time.sleep(30)
        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={"MCP-Protocol-Version": "2025-03-26"},
        )
    # Plain GET without SSE — return capability summary
    return jsonify({
        "name": "onecs-kb-api",
        "version": "1.0.0",
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
