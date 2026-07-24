"""
kb_core.py — Lógica de negócio partilhada da OneCs KB API.

Antes desta refatoração, app.py (REST) e mcp_server.py (MCP) tinham cada
um a SUA PRÓPRIA cópia de praticamente toda a lógica (carregar markdown,
pesquisar, gerir conhecimento dinâmico, gerir versões de tópicos). Isso é
uma fonte garantida de bugs: corriges algo num ficheiro e esqueces o outro.

Este módulo centraliza tudo — app.py e mcp_server.py chamam estas funções
e ficam apenas com a parte de "transporte" (rotas Flask / JSON-RPC MCP).

PERSISTÊNCIA:
  - Conhecimento dinâmico (add_knowledge): Turso quando configurado
    (TURSO_DATABASE_URL + TURSO_AUTH_TOKEN), senão ficheiro JSON local
    (dynamic_knowledge.json) — não persiste em produção sem Turso.
  - Tópicos atualizados (update_topic) e o seu histórico de versões:
    Turso quando configurado (tabelas topic_overrides / topic_versions),
    senão ficheiros locais em versions/ e escrita direta no próprio
    ficheiro .md — também não persiste em produção sem Turso.
"""
import os
import re
import json
from datetime import datetime, timezone

import turso_db


# ------------------------------------------------------------------
# Configuração (injetada uma vez a partir de app.py)
# ------------------------------------------------------------------
class Config:
    base_dir: str = ""
    wiki_data_dir: str = ""
    versions_dir: str = ""
    dynamic_knowledge_file: str = ""
    products: list = []


_cfg = Config()


def init(base_dir, wiki_data_dir, versions_dir, dynamic_knowledge_file, products):
    """Chamado uma vez no arranque da app para injetar os caminhos/configuração."""
    _cfg.base_dir = base_dir
    _cfg.wiki_data_dir = wiki_data_dir
    _cfg.versions_dir = versions_dir
    _cfg.dynamic_knowledge_file = dynamic_knowledge_file
    _cfg.products = products

    os.makedirs(_cfg.versions_dir, exist_ok=True)

    if turso_available():
        try:
            turso_db.init_db()
            turso_db.migrate_from_json(_cfg.dynamic_knowledge_file)
        except Exception as e:
            print(f"[WARN] Turso init/migrate failed: {e}")


def turso_available() -> bool:
    return bool(os.environ.get("TURSO_DATABASE_URL", "").strip()) and bool(
        os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------
# Ficheiros markdown estáticos (wiki_data/<produto>/*.md)
# ------------------------------------------------------------------
def load_all_markdown() -> dict:
    """Lê todos os ficheiros .md de wiki_data/<produto>/, e substitui o
    conteúdo por qualquer override ativo guardado na Turso (tópicos
    atualizados via update_topic). Devolve {caminho_relativo: {content, product}}."""
    all_content = {}
    for product in _cfg.products:
        product_dir = os.path.join(_cfg.wiki_data_dir, product)
        if os.path.isdir(product_dir):
            for fname in os.listdir(product_dir):
                if fname.endswith(".md"):
                    rel = os.path.join(product, fname)
                    full_path = os.path.join(product_dir, fname)
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    all_content[rel] = {"content": content, "product": product}

    if turso_available():
        # Aplica por cima qualquer override guardado (tópicos atualizados)
        for rel, data in list(all_content.items()):
            topic_slug = os.path.splitext(os.path.basename(rel))[0]
            override = turso_db.get_override(topic_slug, data["product"])
            if override is not None:
                all_content[rel]["content"] = override

    return all_content


def find_topic_file(topic: str):
    """Localiza o ficheiro estático correspondente a um tópico em qualquer
    diretório de produto. Devolve (path, product) ou (None, None)."""
    for product in _cfg.products:
        product_dir = os.path.join(_cfg.wiki_data_dir, product)
        if os.path.isdir(product_dir):
            path = os.path.join(product_dir, f"{topic}.md")
            if os.path.exists(path):
                return path, product
            for fname in os.listdir(product_dir):
                if fname.lower() == f"{topic}.md".lower():
                    return os.path.join(product_dir, fname), product
    return None, None


def get_topic_content(topic: str):
    """Devolve (content, product, rel_path) para um tópico, ou (None, None, None)
    se não existir. Se o tópico tiver sido atualizado via update_topic e a
    Turso estiver configurada, devolve o conteúdo atualizado (override) em
    vez do ficheiro estático original."""
    path, product = find_topic_file(topic)
    if path is None:
        return None, None, None

    rel_path = os.path.relpath(path, _cfg.wiki_data_dir)

    if turso_available():
        override = turso_db.get_override(topic, product)
        if override is not None:
            return override, product, rel_path

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return content, product, rel_path


def search_content(query: str, product_filter: str = None) -> list:
    """Pesquisa uma palavra-chave em todos os ficheiros markdown (já com
    overrides aplicados), com filtro de produto opcional."""
    query_lower = query.lower()
    results = []
    all_content = load_all_markdown()
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


def products_summary() -> dict:
    """Lista as categorias de produto com a contagem de páginas .md em cada uma."""
    counts = {}
    for product in _cfg.products:
        product_dir = os.path.join(_cfg.wiki_data_dir, product)
        if os.path.isdir(product_dir):
            md_files = [f for f in os.listdir(product_dir) if f.endswith(".md")]
            counts[product] = len(md_files)
        else:
            counts[product] = 0
    return {"products": _cfg.products, "counts": counts}


# ------------------------------------------------------------------
# Conhecimento dinâmico (Turso ou JSON local)
# ------------------------------------------------------------------
def _load_dynamic_knowledge_json() -> list:
    if not os.path.exists(_cfg.dynamic_knowledge_file):
        return []
    try:
        with open(_cfg.dynamic_knowledge_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _save_dynamic_knowledge_json(entries: list):
    with open(_cfg.dynamic_knowledge_file, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def knowledge_list() -> list:
    """Lista todas as entradas de conhecimento dinâmico (resumo)."""
    if turso_available():
        return turso_db.list_entries()
    return _load_dynamic_knowledge_json()


def knowledge_get(entry_id: int):
    """Devolve uma entrada completa de conhecimento dinâmico, ou None."""
    if turso_available():
        return turso_db.get_entry(entry_id)
    for entry in _load_dynamic_knowledge_json():
        if entry.get("id") == entry_id:
            return entry
    return None


def knowledge_add(data: dict) -> dict:
    """Adiciona uma nova entrada de conhecimento dinâmico. Devolve a entrada criada."""
    if turso_available():
        return turso_db.add_entry(data)

    entries = _load_dynamic_knowledge_json()
    new_id = (max(e["id"] for e in entries) + 1) if entries else 1
    new_entry = {
        "id": new_id,
        "titulo": data.get("titulo"),
        "categoria": data.get("categoria"),
        "conteudo": data.get("conteudo"),
        "tags": data.get("tags", []),
        "fonte": data.get("fonte", "api"),
        "data_criacao": _now_iso(),
        "status": "active",
    }
    entries.append(new_entry)
    _save_dynamic_knowledge_json(entries)
    return new_entry


def knowledge_delete(entry_id: int) -> bool:
    """Remove uma entrada de conhecimento dinâmico. Devolve True se removida."""
    if turso_available():
        return turso_db.delete_entry(entry_id)

    entries = _load_dynamic_knowledge_json()
    original_count = len(entries)
    entries = [e for e in entries if e.get("id") != entry_id]
    if len(entries) == original_count:
        return False
    _save_dynamic_knowledge_json(entries)
    return True


# ------------------------------------------------------------------
# Versionamento de tópicos (Turso ou ficheiros locais)
# ------------------------------------------------------------------
_TIMESTAMP_RE = re.compile(r"(\d{8}T\d{6})_")


def _list_versions_from_files() -> list:
    """Fallback local (sem Turso): lê os backups guardados em versions/."""
    versions = []
    if not os.path.isdir(_cfg.versions_dir):
        return versions
    for fname in os.listdir(_cfg.versions_dir):
        if fname.endswith(".md"):
            match = _TIMESTAMP_RE.search(fname)
            if match:
                topic = fname[:match.start()].rstrip("_")
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


def list_versions() -> list:
    """Lista todas as versões guardadas de todos os tópicos, mais recente primeiro."""
    if turso_available():
        return turso_db.list_versions()
    return _list_versions_from_files()


def list_versions_for_topic(topic: str) -> list:
    """Lista as versões guardadas de um tópico específico, mais recente primeiro."""
    if turso_available():
        return turso_db.list_versions_for_topic(topic)
    return [v for v in _list_versions_from_files() if v["topic"] == topic]


def update_topic(topic: str, conteudo: str, versao: str = None, nota: str = None) -> dict:
    """Substitui o conteúdo de um tópico, guardando uma cópia do conteúdo
    anterior para poder ser revertida mais tarde. Devolve um dict de
    confirmação, ou {"error": ...} se o tópico não existir."""
    path, product = find_topic_file(topic)
    if path is None:
        return {"error": f"Topic '{topic}' not found"}

    conteudo_atual, _, rel_path = get_topic_content(topic)
    conteudo_atual = conteudo_atual or ""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    version_id = versao or timestamp

    if turso_available():
        turso_db.add_version(topic, product, version_id, nota, conteudo_atual)
        turso_db.upsert_override(topic, product, conteudo)
        backup_ref = f"turso:topic_versions (topic={topic}, version={version_id})"
    else:
        backup_filename = f"{topic}_{timestamp}_{version_id}.md"
        backup_path = os.path.join(_cfg.versions_dir, backup_filename)
        if conteudo_atual:
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(conteudo_atual)
        with open(path, "w", encoding="utf-8") as f:
            f.write(conteudo)
        backup_ref = backup_filename

    return {
        "message": "Topic updated successfully",
        "topic": topic,
        "product": product,
        "file": rel_path,
        "backup": backup_ref,
        "version": version_id,
        "note": nota,
    }


def revert_topic(topic: str, version_id: str) -> dict:
    """Reverte um tópico para uma versão anterior guardada. Devolve um
    dict de confirmação, ou {"error": ...}."""
    path, product = find_topic_file(topic)
    if path is None:
        return {"error": f"Topic '{topic}' not found"}

    rel_path = os.path.relpath(path, _cfg.wiki_data_dir)

    if turso_available():
        backup = turso_db.get_version_backup(topic, version_id)
        if backup is None:
            return {"error": f"No version '{version_id}' found for topic '{topic}'"}

        conteudo_atual, _, _ = get_topic_content(topic)
        conteudo_atual = conteudo_atual or ""
        turso_db.add_version(
            topic, product, version_id,
            f"Estado antes de reverter para a versão '{version_id}'",
            conteudo_atual,
        )
        turso_db.upsert_override(topic, product, backup["conteudo_backup"])

        return {
            "message": "Topic reverted successfully",
            "topic": topic,
            "product": product,
            "file": rel_path,
            "restored_version": version_id,
            "restored_timestamp": backup["data_atualizacao"],
        }

    # Fallback local (sem Turso): backups em ficheiros
    matching = [v for v in list_versions_for_topic(topic) if v["version"] == version_id]
    if not matching:
        return {"error": f"No version '{version_id}' found for topic '{topic}'"}

    version_to_restore = matching[0]
    backup_path = os.path.join(_cfg.versions_dir, version_to_restore["filename"])
    if not os.path.exists(backup_path):
        return {"error": f"Backup file not found: {version_to_restore['filename']}"}

    with open(backup_path, "r", encoding="utf-8") as f:
        backup_content = f.read()

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            current_content = f.read()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        pre_backup_filename = f"{topic}_{timestamp}_pre_revert.md"
        with open(os.path.join(_cfg.versions_dir, pre_backup_filename), "w", encoding="utf-8") as f:
            f.write(current_content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(backup_content)

    return {
        "message": "Topic reverted successfully",
        "topic": topic,
        "product": product,
        "file": rel_path,
        "restored_from": version_to_restore["filename"],
        "restored_timestamp": version_to_restore["timestamp"],
        "restored_version": version_to_restore["version"],
    }
