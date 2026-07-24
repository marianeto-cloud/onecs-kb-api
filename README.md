# OneCs Knowledge Base API

API Flask que serve a base de conhecimento da equipa OneCs/OLX para os produtos OLX, Standvirtual, Imovirtual e transversal.

## Estrutura

```
onecs-kb-api/
├── app.py                 # Aplicação Flask — rotas REST + endpoint /mcp (transporte)
├── mcp_server.py           # Protocolo MCP JSON-RPC 2.0 (transporte) — ferramentas MCP
├── kb_core.py              # Lógica de negócio PARTILHADA por app.py e mcp_server.py
├── turso_db.py             # Acesso à base de dados Turso (conhecimento + versões)
├── confluence_sync.py      # Script para sincronizar com Confluence (correr localmente)
├── requirements.txt        # Dependências Python
├── render.yaml             # Configuração do Render
├── dynamic_knowledge.json  # Seed inicial de conhecimento dinâmico (migrado 1x para a Turso)
├── wiki_data/              # Ficheiros markdown organizados por produto
│   ├── olx/
│   ├── standvirtual/
│   ├── imovirtual/
│   └── transversal/
└── versions/               # Backups de versões (fallback local, só usado sem Turso)
```

### Porque é que app.py e mcp_server.py já não têm lógica duplicada

Antes, cada um tinha a sua própria cópia de "carregar markdown", "pesquisar",
"gerir conhecimento dinâmico" e "gerir versões" — o que significava que uma
correção feita num ficheiro facilmente ficava esquecida no outro. Agora,
toda essa lógica vive em `kb_core.py`; `app.py` e `mcp_server.py` são só a
camada de "transporte" (rotas REST vs. JSON-RPC) por cima da mesma lógica.

### Persistência

- **Conhecimento dinâmico** (`add_knowledge`): Turso quando configurado, senão `dynamic_knowledge.json` local.
- **Tópicos atualizados e o seu histórico de versões** (`update_topic` / `revert_topic`): também Turso quando configurado (tabelas `topic_overrides` e `topic_versions`), senão ficheiros locais em `versions/`. Isto é uma mudança em relação à versão anterior, em que o histórico de versões só existia em ficheiros locais — e por isso desaparecia a cada redeploy no Render free tier, mesmo com a Turso configurada para o conhecimento dinâmico.

## Deploy no Render

1. Criar repositório no GitHub e fazer upload de todos os ficheiros
2. No Render, criar um novo **Web Service** e ligar ao repositório GitHub
3. Configurar:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT`
4. Deploy

## Sincronizar com Confluence

O script `confluence_sync.py` deve ser corrido localmente (no Toqan) para descarregar as páginas do espaço "OCP" do Confluence e guardá-las como ficheiros markdown. Depois, fazer commit e push das alterações para o GitHub — o Render faz deploy automático.

## Endpoints

- `GET /` — Informação da API
- `GET /health` — Health check
- `GET /products` — Lista de produtos com contagem de páginas
- `GET /search?q=<query>&product=<product>` — Pesquisa
- `GET /topic/<topic>` — Conteúdo completo de um tópico
- `GET /all` — Todo o conteúdo
- `GET /knowledge` — Entradas dinâmicas
- `POST /knowledge` — Adicionar entrada
- `GET /versions` — Versões guardadas

## Endpoint MCP (Model Context Protocol)

A API expõe um endpoint `/mcp` que implementa o protocolo MCP (JSON-RPC 2.0), permitindo que agentes de IA como o Sir-Motors-A-Lot se conectem e usem as ferramentas automaticamente.

**URL:** `https://onecs-kb-api.onrender.com/mcp`

### Métodos MCP suportados

| Método | Descrição |
|--------|-----------|
| `initialize` | Handshake inicial — devolve capabilities e serverInfo |
| `ping` | Keep-alive |
| `tools/list` | Lista todas as ferramentas disponíveis |
| `tools/call` | Executa uma ferramenta específica |
| `resources/list` | Lista os ficheiros wiki como resources |
| `resources/read` | Lê o conteúdo de um resource específico |

### Ferramentas disponíveis (11)

1. **search** — Pesquisa palavra-chave (`query`, opcional `product`)
2. **topic** — Conteúdo completo de um tópico (`topic`)
3. **all_content** — Todo o conteúdo da base de conhecimento
4. **list_knowledge** — Lista entradas de conhecimento dinâmico
5. **get_knowledge** — Uma entrada específica (`entry_id`)
6. **add_knowledge** — Adiciona nova entrada (`titulo`, `categoria`, `conteudo`, opcional `tags`, `fonte`)
7. **delete_knowledge** — Remove entrada (`entry_id`)
8. **list_versions** — Lista versões guardadas
9. **list_versions_topic** — Versões de um tópico (`topic`)
10. **revert_topic** — Reverte para versão anterior (`topic`, `version`)
11. **products** — Lista categorias de produto com contagem

### Resources disponíveis

Cada ficheiro markdown em `wiki_data/` está exposto como resource com URI `wiki://<produto>/<slug>`.

### Como registar no agente (Toqan/ToqanClaw)

1. Nas **Connections** do agente (Sir-Motors-A-Lot / OneCs Copilot), adicionar uma nova conexão MCP
2. URL do servidor: `https://onecs-kb-api.onrender.com/mcp`
3. Não é necessário token de autenticação — o agente autentica-se nas Connections
4. O agente recebe automaticamente a lista de ferramentas ao conectar

Ver `MCP_SETUP.md` para instruções detalhadas e exemplos de chamadas.
