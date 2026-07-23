---
title: "Bug: Comprador não recebe pedidos de avaliação aos vendedores"
confluence_id: "60729820193"
confluence_url: "https://naspersclassifieds.atlassian.net/wiki/spaces/OCP/pages/60729820193"
synced: "2026-07-25"
product: "olx"
---

Existem 2 situações possíveis de gerar reclamação:

1. **Utilizadores que se queixam ou pedem para avaliar um vendedor em específico**
  - Não é possível enviarmos um pedido para avaliação de um vendedor específico e a equipa de ratings nao dá suporte.
  No entanto, se o utilizador receber um pedido de feedback qualquer e fazer a avaliação até ao fim, tem uma opção que lhe surge para avaliar. Se tiver mais interacções numa semana do que apenas uma, irão aparecer aqui os próximos 3 recentes vendedores. pode ser alteranativa para avaliar um vendedor que queira. Secção: Others awaiting your feedback.

    (Informação interna: Em teoria podem seguir as chain ratings ate extinguir todos os vendedores que contactaram.)

2. **Utilizadores que se queixam que não receberam nenhum pedido de feedback depois de terem conversas com um ou mais vendedores**

  Importa despistar primeiro (antes de reportar em slack) de que forma foi feita o negócio:
  **computador:** deve verificar a caixa de entrada do email e o spam.
  *confirmar com o user qual o endereço de email da conta OLX onde foi feito o negócio, caso ele não indique o id do anúncio a que se refere.

  **Aplicação:** recebe uma push notification para avaliar - nao vai receber por email.
  importa confirmar que no equipamento do cliente, se tem a App OLX com permissão para notificar, e não tem bloqueadas no telefone.
  - **Em Salesforce, case PENDING.**
3. Os casos que seriam para reportar seriam os utilizadores (com contas há mais de 30 dias) que reportam não ter recebido **quaisquer** pedidos de feedback **(num prazo de 7 dias)** depois de terem tido interações do tipo (para o caso de PT):

*  Meaningful conversations: Dentro de 24H têm de ter falado com um vendedor, recebido resposta e mandado outra mensagem
* Show number interactions: Clicado em ver numero ou fazer chamada/sms

**4 .** Apenas precisam do **user-id dos utilizadores** que reportaram o problema no canal de **slack** [**#eu-buyer-support **](https://olxgroup.enterprise.slack.com/archives/C037BDFGPGE)e a equipa de ratings cria o ticket de análise.

O case em Salesforce fica **ON-HOLD.**