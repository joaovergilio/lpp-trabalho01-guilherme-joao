# Porto de Pesca em Tempo Real

Trabalho 01 de Linguagem de Programação e Paradigmas (2026/2), Programação Orientada a Eventos.
**Tipo de vila (sorteio): 4, Porto de pesca.** O peixe fresco vira peixe salgado; as construções são barco, salga e cais; os trabalhadores são pescadores; e o pescado estraga se não for salgado a tempo.

## Integrantes
- Guilherme Losi: @guilhermelosi-lab
- João Vitor Vergilio: @joaovergilio

## Linguagem e bibliotecas
- **Servidor:** Python 3 com `python-socketio` e `uvicorn`. O estado fica só na memória.
- **Tela:** HTML e JavaScript com Vue 3, cliente Socket.IO e Phaser 3, todos carregados por CDN (como no Kit Inicial).

## Como instalar e executar
Pré-requisitos: Python 3.10 ou mais novo e Git.

```bash
git clone https://github.com/SEU-USUARIO/lpp-trabalho01-guilherme-joao.git
cd lpp-trabalho01-guilherme-joao
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux ou macOS
pip install -r requirements.txt
uvicorn server:app --reload
```

Abra **http://localhost:8000** no navegador. Use o endereço, e não o arquivo direto pelo `file://`.
Se o servidor reiniciar, o porto volta ao começo. Nesse caso, recarregue as abas.

## Como testar com duas abas (ou três, para a disputa)
1. **Aba 1:** digite um nome e clique em **Entrar como Mestre do porto**. **Aba 2:** digite outro nome e clique em **Entrar como Pescador**. As duas mostram 60 🐟, a faixa "Aguardando o Mestre do porto" e o evento `⬇ on estado.sincronizado` (causa: `conexao`).
2. **Recusa antes da abertura:** na aba do Pescador, clique em **Construir Barco**. Só essa aba recebe o aviso vermelho "A temporada de pesca não está aberta", a vila treme e aparece `⬇ on operacao.recusada`. A aba do Mestre não recebe nada.
3. **Abertura:** o Mestre clica em **Abrir temporada de pesca**. Nas duas abas a faixa muda para "☀️ Temporada de pesca aberta" e aparece o primeiro lote de peixe, com a barra de validade. O Mestre vê `⬆ emit vila.abertura_solicitada` e `⬇ on vila.iniciada`; o Pescador vê só o `⬇ on`.
4. **Construir:** o Pescador clica em **Construir Salga** (40 🐟). As duas abas mostram 20 🐟, os pescadores em 1/3 e o canteiro com barra de progresso.
5. **Passagem do tempo:** sem ninguém clicar, a cada 5 s chega `recurso.produzido` (+10 🐟, causa: temporizador da pescaria). Depois de 8 s chega `construcao.concluida`, o canteiro vira a salga e, nas pescarias seguintes, aparece `pescado.salgado` (causa: `recurso.produzido`).
6. **O que expira:** se ninguém construir uma salga, 20 s depois da abertura o lote inicial estraga e todos recebem `pescado.estragado`: o peixe fresco cai e os estragados sobem.
7. **Disputa (três abas: Mestre, Pescador A e Pescador B):** deixe 2 de 3 pescadores ocupados e clique em construir nas abas A e B quase ao mesmo tempo. Só uma recebe a obra (3/3); a outra vê "Sem pescador livre". Também dá para testar com exatamente 30 🐟 e dois pedidos de barco: só um passa e o estoque nunca fica negativo.
8. **Encerramento:** o Mestre clica em **Encerrar temporada**. Todos veem `vila.encerrada`, o porto escurece, a pescaria e o prazo dos lotes param e qualquer pedido de construção é recusado.

Marque "ocultar recurso.produzido e pescado.salgado" no Painel de eventos se eles atrapalharem a leitura. Os contadores por evento ficam no alto do painel.

## Regras do porto (resumo)
As regras completas estão em [`docs/especificacao.md`](docs/especificacao.md).

| Construção | Custo | Obra | Efeito ao concluir |
|---|---|---|---|
| ⛵ Barco | 30 🐟 fresco | 6 s | +5 peixes por pescaria |
| 🧂 Salga | 40 🐟 fresco | 8 s | salga 8 peixes por pescaria |
| ⚓ Cais | 15 🧂 salgado | 10 s | +1 pescador no limite |

O porto começa com 60 🐟 e 3 pescadores. A pescaria acontece a cada 5 s e traz 10 🐟, mais 5 por barco. Cada lote de peixe fresco estraga 20 s depois de chegar. A salga e as obras sempre usam os lotes mais antigos primeiro.

## Perguntas

### 1. Quais eventos o seu sistema emite e escuta?

| Evento | Quem emite | Quem escuta |
|---|---|---|
| `estado.sincronizado` | Servidor, ao conectar | Só o cliente que entrou |
| `vila.abertura_solicitada` | Cliente do Mestre (pedido) | Servidor |
| `vila.iniciada` | Servidor | Todos |
| `construcao.solicitada` (com `tipo`) | Cliente do Pescador (pedido) | Servidor |
| `construcao.iniciada` | Servidor | Todos |
| `operacao.recusada` | Servidor | Só quem pediu |
| `recurso.produzido` | Servidor (temporizador da pescaria) | Todos |
| `pescado.salgado` | Servidor (encadeado na pescaria) | Todos |
| `pescado.estragado` | Servidor (temporizador do prazo do lote) | Todos |
| `construcao.concluida` | Servidor (temporizador da obra) | Todos |
| `vila.encerramento_solicitado` | Cliente do Mestre (pedido) | Servidor |
| `vila.encerrada` | Servidor | Todos |

Os pedidos terminam em `_solicitada`/`_solicitado` e só o cliente os emite. Os fatos (no passado) só o servidor emite. A recusa também é um evento, `operacao.recusada`, enviado apenas para quem fez o pedido.

### 2. Como o sistema sabe quando deve atualizar os outros jogadores?
O cliente nunca pergunta se algo mudou. Toda mudança de estado acontece no servidor, dentro de um handler de evento (um pedido) ou de um temporizador. Logo depois de mudar o estado, o servidor emite o fato com `sio.emit(...)` sem destino, e o Socket.IO entrega a todos os clientes conectados. Quando o fato só interessa a um cliente (a recusa e a sincronização de quem acabou de entrar), o servidor usa `to=sid`. No cliente, cada `ouvir("evento", ...)` copia o estado recebido com `atualizar(d)`. O Vue redesenha o painel sozinho e o Phaser roda a reação na vila. Cada fato leva junto a sua **causa**, que aparece no Painel de eventos.

### 3. Que parte do código mostra claramente o uso do paradigma orientado a eventos?
- **`server.py`, `construir()`**: escuta `construcao.solicitada`, valida tudo sem `await` entre a validação e a alteração (por isso a disputa tem um vencedor só) e reage emitindo `construcao.iniciada` para todos ou `operacao.recusada` só para quem pediu.
- **`server.py`, `pescaria()`, `prazo_do_lote()` e `obra()`**: temporizadores como fonte de eventos. Eles emitem `recurso.produzido`, `pescado.salgado`, `pescado.estragado` e `construcao.concluida` sem que ninguém clique. A salga é encadeada na pescaria, e a causa dela é `recurso.produzido`.
- **`client/index.html`, região ESCUTAS dentro de `entrar()`**: cada `ouvir(evento, reação, função)` liga um fato do servidor a uma reação na tela e na vila. A região PEDIDOS (`abrirVila`, `construir`, `encerrarVila`) só emite pedidos com `pedir(...)`.

## Uso de IA
Usamos o **Claude (Anthropic)** como apoio para escrever a especificação, o código do servidor e do cliente a partir do Kit Inicial e do Guia de Implementação, as peças de pixel art do porto (geradas por script) e este README.
**O que mudamos / revisamos:** não alteramos a lógica do código gerado. Nossa parte foi conferir se a implementação seguia o enunciado, o Guia de Implementação e o nosso tipo de vila (Porto de pesca), testar o sistema com várias abas abertas (Mestre e dois Pescadores) seguindo os cenários da especificação, completar os dados dos integrantes e publicar o repositório. Também estudamos o código para entender cada evento: quem emite, quem escuta e o que muda no estado.  


## Extras
- **Recurso refinado:** 🧂 peixe salgado, produzido pela salga a partir do peixe fresco e usado para pagar o cais.
- **Eventos próprios:** `pescado.salgado` (encadeado em `recurso.produzido`) e `pescado.estragado` (o que expira no porto: lotes com prazo de 20 s).
- **Três tipos de construção** com custos, tempos e efeitos diferentes. O cais aumenta o limite de pescadores.
- **Lotes de pescado com barra de validade** na tela. A barra é só animação CSS a partir do tempo que o servidor informa, então o cliente não fica verificando nada.
- **Mapa personalizado** (praia, mar, píer, boias) e sprites de barco, salga e cais, com o barco balançando na água.
- **Contadores por evento** no Painel de eventos (obrigatório para dupla).

## Créditos de arte
- Grama, caminho, água com margem de grama, árvores, casa e canteiro: arte original do Kit Inicial da disciplina.
- Areia, píer, caixas, barris, redes, boias, âncora, água com margem de areia e os sprites de barco, salga e cais: arte original criada para este trabalho (pixel art desenhada por script, com apoio de IA). Uso livre. Detalhes em `client/assets/LEIA-ME.txt`.
