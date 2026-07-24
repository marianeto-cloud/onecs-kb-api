# Configurar Turso para a OneCs KB API

> **Nota sobre a versão 2.0 deste projeto:** foram corrigidos 3 bugs reais
> que impediam a Turso de funcionar corretamente:
> 1. `requirements.txt` instalava o pacote `libsql-client` (descontinuado
>    pela Turso), mas o código fazia `import libsql` (pacote diferente) —
>    por isso a ligação "boa" nunca era usada, caindo sempre no fallback
>    HTTP manual.
> 2. Esse fallback HTTP não convertia os números devolvidos pela Turso (que
>    vêm como texto, ex: `"0"`) de volta para `int`/`float`, causando erros
>    como `'>' not supported between instances of 'str' and 'int'`.
> 3. O histórico de versões de tópicos (`update_topic`/`revert_topic`) só
>    existia em ficheiros locais, mesmo com a Turso configurada — por isso
>    desaparecia a cada redeploy no Render free tier. Agora também vive na
>    Turso (tabelas `topic_overrides` e `topic_versions`).

Este guia explica como criar uma base de dados Turso e configurá-la na OneCs KB API para garantir que o conhecimento dinâmico persiste entre restarts do Render free tier.

---

## 1. Criar uma conta no Turso

1. Vai a [turso.tech](https://turso.tech) e cria uma conta gratuita.
2. Instala o CLI do Turso:
   ```sh
   curl -L https://get.tur.so/install.sh | bash
   ```
3. Faz login:
   ```sh
   turso login
   ```

---

## 2. Criar uma base de dados Turso

### Opção A: Com o CLI (recomendado)

```sh
# Criar a base de dados
turso db create onecs-kb-api --region eu-frankfurt

# Obter a URL da base de dados
turso db show onecs-kb-api --url
# Exemplo: libsql://onecs-kb-api-eu-frankfurt.turso.io

# Criar um token de autenticação
turso db tokens create onecs-kb-api
# Guarda o token gerado — não será mostrado novamente
```

### Opção B: Usar uma base de dados existente

Se já tens uma base de dados Turso que queres usar:

```sh
# Lista as tuas bases de dados
turso db list

# Mostra os detalhes (inclui a URL)
turso db show <nome-da-db>

# Cria um token para esta base de dados
turso db tokens create <nome-da-db>
```

---

## 3. Obter a URL e o Token

Depois de criar a base de dados, precisas de dois valores:

| Variável | Como obter | Exemplo |
|---|---|---|
| `TURSO_DATABASE_URL` | `turso db show <nome> --url` | `libsql://onecs-kb-api-eu-frankfurt.turso.io` |
| `TURSO_AUTH_TOKEN` | `turso db tokens create <nome>` | `eyJhbGciOiJFZERTQSJ...` (token JWT longo) |

**Importante:** O token é sensível — não o partilhes publicamente.

---

## 4. Configurar no Render Dashboard

1. Vai a [dashboard.render.com](https://dashboard.render.com) e abre o serviço **onecs-kb-api**.
2. Clica em **Environment** no menu lateral.
3. Adiciona as seguintes variáveis de ambiente:

   | Chave | Valor | Sync |
   |---|---|---|
   | `TURSO_DATABASE_URL` | URL da tua base de dados (ex: `libsql://onecs-kb-api-eu-frankfurt.turso.io`) | **Off** |
   | `TURSO_AUTH_TOKEN` | O token JWT gerado | **Off** |

   > ⚠️ Marca **Sync: Off** para que o Render não sobreponha o valor ao que vais inserir manualmente.

4. Clica **Save Changes**.
5. O Render vai fazer deploy automaticamente ou clica em **Manual Deploy → Deploy latest commit**.

---

## 5. Verificar que funciona

Depois do deploy, testa os endpoints de conhecimento dinâmico:

```sh
# Lista entradas (deve mostrar pelo menos 1 entrada de seed)
curl https://<teu-servico>.onrender.com/knowledge

# Cria uma nova entrada
curl -X POST https://<teu-servico>.onrender.com/knowledge \
  -H "Content-Type: application/json" \
  -d '{"titulo":"Teste","categoria":"procedimentos","conteudo":"Teste de integração Turso"}'

# Verifica que foi guardada
curl https://<teu-servico>.onrender.com/knowledge
```

No JSON de resposta do endpoint `/`, o campo `"storage"` deve ser `"turso"` quando as variáveis estão configuradas.

---

## 6. Notas técnicas

- **libsql-client**: a API usa o pacote Python `libsql-client` (versão ≥ 0.3.0). Se não estiver disponível, faz fallback automático para a HTTP API do Turso usando `urllib`.
- **Sem Turso**: se `TURSO_DATABASE_URL` ou `TURSO_AUTH_TOKEN` não estiverem definidas, a API volta a usar o ficheiro `dynamic_knowledge.json` (desenvolvimento local).
- **Migração automática**: ao iniciar com Turso configurado, se a tabela `knowledge_entries` estiver vazia, a API migra automaticamente as entradas do `dynamic_knowledge.json` para o Turso.
- **Persistência**: com o Render free tier, o sistema de ficheiros é efémero — o Turso resolve este problema.

---

## 7. Comandos úteis do Turso CLI

```sh
# Ver info da base de dados
turso db show onecs-kb-api

# Listar bases de dados
turso db list

# Criar novo token (os antigos podem ser revogados)
turso db tokens create onecs-kb-api

# Ver tokens existentes
turso db tokens list onecs-kb-api

# Revogar um token
turso db tokens revoke onecs-kb-api <token-id>

# Verificar conectividade
turso db shell onecs-kb-api "SELECT 1;"
```
