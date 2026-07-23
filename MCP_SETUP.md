# Guia de Configuração MCP — OneCs KB API

## O que é o MCP?

O **Model Context Protocol (MCP)** é um protocolo standard que permite a agentes de IA (como o Sir-Motors-A-Lot) conectar-se a servidores de ferramentas e aceder a recursos de forma estruturada — sem necessidade de conhecer cada endpoint REST individualmente.

O agente conecta-se ao endpoint `/mcp`, recebe a lista de ferramentas disponíveis, e pode invocá-las diretamente através de chamadas JSON-RPC 2.0.

## Endpoint MCP

```
https://onecs-kb-api.onrender.com/mcp
```

- **Método:** POST (JSON-RPC 2.0)
- **Content-Type:** `application/json`
- **Autenticação:** Nenhuma (o agente autentica-se nas Connections do Toqan/ToqanClaw)
- **Versão do protocolo:** `2025-03-26`

---

## Ferramentas Disponíveis

### 1. search
Pesquisa palavra-chave em todos os documentos da base de conhecimento.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `query` | string | ✅ | Palavra ou expressão a pesquisar |
| `product` | string | ❌ | Filtro: `olx`, `standvirtual`, `imovirtual`, `transversal` |

**Exemplo:**
```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "reembolso"}}}
```

---

### 2. topic
Devolve o conteúdo completo de um tópico específico.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `topic` | string | ✅ | Nome do tópico (slug do ficheiro .md) |

**Tópicos válidos:** `pacotes`, `destaques`, `reembolso`, `termos`, `procedimentos`, `moderacao`, `contas`, `tecnicos`, `fraude`, `servicos`, `templates`, `casos`, `referencias`, `saldo`, `verificar`, `comunicacao`, `standvirtual`, `verificar-controlauto` (e qualquer ficheiro .md em `wiki_data/`)

**Exemplo:**
```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "topic", "arguments": {"topic": "reembolso"}}}
```

---

### 3. all_content
Devolve todo o conteúdo da base de conhecimento — todos os ficheiros markdown.

```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "all_content", "arguments": {}}}
```

---

### 4. list_knowledge
Lista todas as entradas de conhecimento dinâmico (resumo, sem conteúdo completo).

```json
{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "list_knowledge", "arguments": {}}}
```

---

### 5. get_knowledge
Devolve uma entrada específica de conhecimento dinâmico.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `entry_id` | integer | ✅ | ID da entrada |

```json
{"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "get_knowledge", "arguments": {"entry_id": 1}}}
```

---

### 6. add_knowledge
Adiciona uma nova entrada de conhecimento dinâmico.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `titulo` | string | ✅ | Título curto |
| `categoria` | string | ✅ | Categoria (ex: `casos`, `procedimentos`, `faq`, `templates`) |
| `conteudo` | string | ✅ | Conteúdo completo |
| `tags` | string | ❌ | Etiquetas separadas por vírgulas |
| `fonte` | string | ❌ | Origem da informação |

```json
{"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "add_knowledge", "arguments": {"titulo": "Caso #17 - Anúncio duplicado", "categoria": "casos", "conteudo": "Descrição do caso...", "tags": "duplicado,anúncio", "fonte": "Sir-Motors-A-Lot"}}}
```

---

### 7. delete_knowledge
Remove uma entrada de conhecimento dinâmico.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `entry_id` | integer | ✅ | ID da entrada a remover |

```json
{"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "delete_knowledge", "arguments": {"entry_id": 17}}}
```

---

### 8. list_versions
Lista todas as versões guardadas de todos os tópicos (mais recente primeiro).

```json
{"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "list_versions", "arguments": {}}}
```

---

### 9. list_versions_topic
Lista as versões guardadas de um tópico específico.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `topic` | string | ✅ | Nome do tópico |

```json
{"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "list_versions_topic", "arguments": {"topic": "reembolso"}}}
```

---

### 10. revert_topic
Reverte um tópico para uma versão anterior guardada.

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `topic` | string | ✅ | Nome do tópico a reverter |
| `version` | string | ✅ | Identificador da versão (retornado por `list_versions_topic`) |

```json
{"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "revert_topic", "arguments": {"topic": "reembolso", "version": "20250601T120000"}}}
```

---

### 11. products
Lista as 4 categorias de produto com a contagem de páginas em cada uma.

```json
{"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "products", "arguments": {}}}
```

---

## Resources Disponíveis

Cada ficheiro markdown em `wiki_data/` está exposto como um **resource** com URI:

```
wiki://<produto>/<slug>
```

Por exemplo:
- `wiki://olx/contactos`
- `wiki://standvirtual/tarifario`
- `wiki://imovirtual/suporte`
- `wiki://transversal/politicas`

### Listar resources
```json
{"jsonrpc": "2.0", "id": 12, "method": "resources/list", "params": {}}
```

### Ler um resource
```json
{"jsonrpc": "2.0", "id": 13, "method": "resources/read", "params": {"uri": "wiki://standvirtual/tarifario"}}
```

---

## Exemplos com curl

### Inicializar ligação
```bash
curl -s -X POST https://onecs-kb-api.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

### Listar ferramentas
```bash
curl -s -X POST https://onecs-kb-api.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

### Pesquisar "reembolso"
```bash
curl -s -X POST https://onecs-kb-api.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search","arguments":{"query":"reembolso"}}}'
```

### Obter tópico "reembolso"
```bash
curl -s -X POST https://onecs-kb-api.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"topic","arguments":{"topic":"reembolso"}}}'
```

### Listar versões de "reembolso"
```bash
curl -s -X POST https://onecs-kb-api.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"list_versions_topic","arguments":{"topic":"reembolso"}}}'
```

### Ping (keep-alive)
```bash
curl -s -X POST https://onecs-kb-api.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":6,"method":"ping","params":{}}'
```

---

## Como registar no Agente (Toqan/ToqanClaw)

### Sir-Motors-A-Lot / OneCs Copilot

1. Abre as **Connections** do agente no Toqan/ToqanClaw
2. Clica em **Adicionar conexão** → **MCP Server**
3. Preenche:
   - **Nome:** OneCs KB API
   - **URL do servidor:** `https://onecs-kb-api.onrender.com/mcp`
   - **Autenticação:** Nenhuma (deixar em branco)
4. Clica **Guardar** — o agente recebe automaticamente a lista de ferramentas
5. O agente pode agora usar as ferramentas MCP diretamente, por exemplo:
   - `/search reembolso` → chama a ferramenta `search`
   - `/topic reembolso` → chama a ferramenta `topic`

### Verificar a ligação

 Faz um GET para `/mcp`:
```bash
curl -s https://onecs-kb-api.onrender.com/mcp | python3 -m json.tool
```

Deverás ver:
```json
{
    "name": "onecs-kb-api",
    "version": "1.0.0",
    "mcp_protocol_version": "2025-03-26",
    "mcp_endpoint": "/mcp",
    "capabilities": {
        "tools": {"list": true, "call": true},
        "resources": {"list": true, "read": true}
    },
    "tools_available": 11,
    "resources_available": 220
}
```

---

## Notas Técnicas

- O MCP é implementado sem o pacote oficial `mcp` — apenas Flask + stdlib Python
- Formato: **JSON-RPC 2.0** standard
- Todas as respostas incluem o header `MCP-Protocol-Version: 2025-03-26`
- O agente autentica-se nas Connections do Toqan (não requer API key)
- O storage de conhecimento dinâmico usa **Turso** quando configurado, ou **JSON** como fallback
