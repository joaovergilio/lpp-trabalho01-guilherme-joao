# Especificação — Porto de Pesca em Tempo Real

**Integrantes:** Guilherme Losi (@usuario-github-guilherme) e João Vitor Vergilio (@usuario-github-joao)
**Tipo de vila (sorteio):** 4 — Porto de pesca (peixe → peixe salgado; cais, salga e barco; pescadores; o pescado estraga sem salga)

> Documento escrito antes do código. Descreve o comportamento na linguagem do porto, sem citar tecnologia.

## 1. Regras do porto

- **Papéis:** o **Mestre do porto** abre e encerra a temporada de pesca. O **Pescador** (jogador) pede construções.
- **Recurso primário:** 🐟 **peixe fresco**. **Recurso refinado:** 🧂 **peixe salgado**.
- **Estoque inicial:** 60 peixes frescos e 0 peixes salgados.
- **Trabalhadores:** pescadores. O limite inicial é **3**. Cada obra ocupa 1 pescador do início ao fim da obra.
- **Pescaria (produção automática):** a cada **5 segundos**, com a temporada aberta, os barcos trazem **10 peixes frescos**, mais **5** por barco já concluído. Cada pescaria chega ao porto como um **lote de pescado**.
- **Salga (refino automático):** logo depois de cada pescaria, cada salga concluída transforma até **8 peixes frescos** em **8 peixes salgados**. A salga sempre usa os lotes mais antigos primeiro.
- **O que expira:** cada lote de pescado fresco **estraga 20 segundos** depois de chegar (o estoque inicial começa a contar quando a temporada abre). O que sobrou do lote é perdido e somado aos "estragados". O peixe salgado não estraga.
- **Gasto de peixe fresco:** quando uma obra paga com peixe fresco, o porto usa os lotes mais antigos primeiro.

### Construções

| Construção | Custo | Tempo da obra | O que muda quando a obra termina |
|---|---|---|---|
| ⛵ Barco | 30 peixes frescos | 6 s | a pescaria rende +5 peixes |
| 🧂 Salga | 40 peixes frescos | 8 s | +8 peixes salgados por pescaria (transforma peixe fresco) |
| ⚓ Cais | 15 peixes salgados | 10 s | o limite de pescadores sobe +1 |

- Ao terminar qualquer obra, o pescador volta a ficar livre.
- Pedidos de construção só são aceitos com a temporada **aberta**, com recurso suficiente e com pescador livre. Só o Pescador constrói.
- Quando a temporada é encerrada, a pescaria, a salga e o estrago param, e as obras em andamento não terminam mais.

## 2. Eventos

Padrão de nomes: `objeto.acao_solicitada` para pedidos e `objeto.acao_no_passado` para fatos do porto.

| Evento | Emite | Recebe | O que muda no estado |
|---|---|---|---|
| `estado.sincronizado` | Servidor | Só quem entrou | Nada muda; quem entrou recebe o estado atual do porto |
| `vila.abertura_solicitada` | Mestre | Servidor | (é um pedido; nada muda) |
| `vila.iniciada` | Servidor | Todos | Fase passa para "aberta"; o estoque inicial vira o primeiro lote de pescado; a pescaria começa |
| `construcao.solicitada` | Pescador | Servidor | (é um pedido com o tipo: barco, salga ou cais; nada muda) |
| `construcao.iniciada` | Servidor | Todos | Debita o custo (peixe fresco ou salgado), ocupa 1 pescador e inicia a obra |
| `operacao.recusada` | Servidor | Só quem pediu | Nada muda; informa o motivo (temporada fechada, falta de peixe, sem pescador livre, papel errado) |
| `recurso.produzido` | Servidor | Todos | A pescaria chegou: o peixe fresco sobe e um novo lote de pescado começa a contar o prazo |
| `pescado.salgado` | Servidor | Todos | Logo após a pescaria, as salgas transformam peixe fresco em peixe salgado |
| `pescado.estragado` | Servidor | Todos | O prazo de um lote venceu: o peixe fresco que sobrou dele é perdido e somado aos estragados |
| `construcao.concluida` | Servidor | Todos | A obra termina: o pescador fica livre e o efeito da construção é aplicado |
| `vila.encerramento_solicitado` | Mestre | Servidor | (é um pedido; nada muda) |
| `vila.encerrada` | Servidor | Todos | Fase passa para "encerrada"; novas ações são recusadas e os relógios param |

Cada fato informa a sua **causa**: o pedido que o gerou (por exemplo `construcao.solicitada`) ou o relógio que o gerou (a pescaria, o fim da obra ou o prazo do lote).

## 3. Cenários de teste

### Recusa
**Dado** que a temporada está aberta, há 20 peixes frescos e 2 de 3 pescadores ocupados, **quando** o Pescador A emite `construcao.solicitada` com o tipo "salga" (custa 40), **então** o servidor emite `operacao.recusada` com o motivo "peixe fresco insuficiente" **apenas para A**, e o estoque e os pescadores continuam iguais para todos.

**Dado** que a temporada ainda não foi aberta, **quando** o Pescador A emite `construcao.solicitada`, **então** só A recebe `operacao.recusada` com o motivo "a temporada de pesca não está aberta".

### Passagem do tempo
**Dado** que a temporada está aberta, há 1 barco e 1 salga concluídos e 60 peixes frescos, **quando** passam 5 segundos sem nenhum pedido, **então** o servidor emite `recurso.produzido` para todos (causa: pescaria) com +15 peixes frescos e, logo em seguida, `pescado.salgado` (causa: `recurso.produzido`) transformando 8 peixes frescos em 8 salgados.

**Dado** que um lote de 10 peixes chegou e ninguém o usou nem o salgou, **quando** passam 20 segundos, **então** o servidor emite `pescado.estragado` para todos (causa: prazo do lote), o peixe fresco cai 10 e os estragados sobem 10.

**Dado** que o Pescador A teve uma obra de barco iniciada, **quando** passam 6 segundos, **então** o servidor emite `construcao.concluida` para todos (causa: `construcao.iniciada`), o pescador fica livre e a pescaria passa a render +5.

### Disputa entre dois jogadores
**Dado** que há 2 de 3 pescadores ocupados e peixe suficiente para duas obras, **quando** os pescadores A e B emitem `construcao.solicitada` ao mesmo tempo, **então** o servidor trata um pedido de cada vez: emite `construcao.iniciada` para todos por causa de um deles (3/3 ocupados) e `operacao.recusada` ("sem pescador livre") apenas para o outro.

**Dado** que há exatamente 30 peixes frescos e pescadores livres, **quando** A e B pedem um barco (30 peixes cada) ao mesmo tempo, **então** só um recebe a obra e o outro recebe `operacao.recusada` ("peixe fresco insuficiente"); o estoque nunca fica negativo.
