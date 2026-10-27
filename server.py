"""
Porto de Pesca em Tempo Real — servidor.

O servidor é a FONTE DA VERDADE: guarda o estado do porto na memória, decide
cada pedido e EMITE os fatos para os clientes. Os clientes só pedem e mostram.

Fontes de eventos do servidor:
  1. pedidos dos clientes (@sio.on("..._solicitada"));
  2. temporizadores (pescaria a cada INTERVALO, fim de obra, prazo do pescado).
"""
import itertools
import time
from collections import deque

import socketio

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app = socketio.ASGIApp(sio, static_files={
    "/": "client/index.html",
    "/assets": "client/assets",      # mapa, tileset e sprites do porto
})

# =====================================================================
#  REGRAS DO PORTO (iguais às de docs/especificacao.md)
# =====================================================================
INTERVALO = 5            # segundos entre as pescarias
PRAZO_PESCADO = 20       # segundos até um lote de peixe fresco estragar
PESCA_BASE = 10          # peixes por pescaria sem nenhum barco
LIMITE_INICIAL = 3       # pescadores disponíveis no começo

# Catálogo das construções: custo, recurso usado para pagar, tempo e efeito.
CONSTRUCOES = {
    "barco": {"nome": "Barco", "emoji": "⛵", "custo": 30, "recurso": "peixe",
              "tempo": 6, "efeito": "+5 peixes por pescaria"},
    "salga": {"nome": "Salga", "emoji": "🧂", "custo": 40, "recurso": "peixe",
              "tempo": 8, "efeito": "salga 8 peixes por pescaria"},
    "cais":  {"nome": "Cais", "emoji": "⚓", "custo": 15, "recurso": "salgado",
              "tempo": 10, "efeito": "+1 pescador no limite"},
}

estado = {
    "fase": "aguardando",        # aguardando -> aberta -> encerrada
    "peixe": 60,                 # 🐟 peixe fresco (recurso primário)
    "salgado": 0,                # 🧂 peixe salgado (recurso refinado)
    "estragados": 0,             # total de peixes perdidos por falta de salga
    "pescadores": 0,             # pescadores ocupados agora
    "limite": LIMITE_INICIAL,    # máximo de pescadores
    "producao": PESCA_BASE,      # peixes por pescaria
    "salga_por_ciclo": 0,        # peixes salgados por pescaria
    "intervalo": INTERVALO,
    "prazo": PRAZO_PESCADO,
    "concluidas": {"barco": 0, "salga": 0, "cais": 0},
    "catalogo": CONSTRUCOES,
}

jogadores = {}          # sid -> {"nome": ..., "papel": ...}
obras = {}              # id da obra -> {"tipo", "vaga", "por", "fim"}
predios = []            # construções prontas: [{"tipo", "vaga"}] (para desenhar a vila)
vagas = {"barco": 0, "salga": 0, "cais": 0}   # próxima vaga do mapa de cada tipo
lotes = deque()         # lotes de peixe fresco, do mais antigo ao mais novo
ids = itertools.count(1)


def agora():
    return time.monotonic()


def foto():
    """Cópia do estado para enviar aos clientes (com obras e lotes e o tempo que falta)."""
    t = agora()
    return {
        **estado,
        "concluidas": dict(estado["concluidas"]),
        "em_obra": len(obras),
        "obras": [{"id": i, "tipo": o["tipo"], "vaga": o["vaga"],
                   "restante": round(max(0, o["fim"] - t), 1)} for i, o in obras.items()],
        "predios": list(predios),
        "lotes": [{"id": l["id"], "qtd": l["qtd"],
                   "restante": round(max(0, l["vence"] - t), 1)} for l in lotes],
    }


def fato(causa, **extras):
    """Monta o payload de um FATO: o estado atual, a CAUSA (o pedido ou o
    temporizador que gerou o fato) e dados extras."""
    return {"estado": foto(), "causa": causa, **extras}


@sio.event
async def connect(sid, environ, auth):
    auth = auth or {}
    jogadores[sid] = {
        "nome": auth.get("nome") or "Anônimo",
        "papel": auth.get("papel", "jogador"),
    }
    # servidor -> UM cliente: só quem acabou de entrar precisa do estado atual
    await sio.emit("estado.sincronizado", fato("conexao"), to=sid)


@sio.event
async def disconnect(sid, *args):
    jogadores.pop(sid, None)


async def recusar(sid, motivo, causa):
    """A recusa também é um EVENTO, mas vai só para quem pediu (to=sid)."""
    await sio.emit("operacao.recusada", {"motivo": motivo, "causa": causa}, to=sid)


# ---------------------------------------------------------------------
#  Mestre abre a temporada de pesca
# ---------------------------------------------------------------------
@sio.on("vila.abertura_solicitada")          # escuta o PEDIDO do Mestre
async def abrir_vila(sid, dados=None):
    pedido = "vila.abertura_solicitada"
    if jogadores[sid]["papel"] != "mestre":
        await recusar(sid, "Só o Mestre do porto pode abrir a temporada", pedido)
        return
    if estado["fase"] != "aguardando":
        await recusar(sid, "A temporada de pesca já foi aberta", pedido)
        return
    estado["fase"] = "aberta"
    # FATO para todos: a temporada começou
    await sio.emit("vila.iniciada", fato(pedido))


# ---------------------------------------------------------------------
#  Pedido e fato: construir (barco, salga ou cais)
# ---------------------------------------------------------------------
def consumir_peixe(qtd):
    """Tira `qtd` peixes frescos do estoque, sempre dos lotes MAIS ANTIGOS.
    Função comum (sem await): roda inteira antes de qualquer outro evento."""
    usado = 0
    while lotes and usado < qtd:
        lote = lotes[0]
        tira = min(lote["qtd"], qtd - usado)
        lote["qtd"] -= tira
        usado += tira
        if lote["qtd"] == 0:
            lotes.popleft()
    estado["peixe"] -= qtd
    return usado


@sio.on("construcao.solicitada")             # escuta o PEDIDO do Pescador
async def construir(sid, dados=None):
    pedido = "construcao.solicitada"
    tipo = (dados or {}).get("tipo")
    regra = CONSTRUCOES.get(tipo)

    # Valide TUDO antes de alterar o estado e SEM await no meio:
    # assim, dois pedidos simultâneos são decididos um de cada vez (disputa).
    if estado["fase"] != "aberta":
        motivo = "A temporada de pesca não está aberta"
    elif jogadores[sid]["papel"] != "jogador":
        motivo = "Só o Pescador constrói"
    elif regra is None:
        motivo = "Construção desconhecida"
    elif regra["recurso"] == "peixe" and estado["peixe"] < regra["custo"]:
        motivo = f"Peixe fresco insuficiente (precisa de {regra['custo']})"
    elif regra["recurso"] == "salgado" and estado["salgado"] < regra["custo"]:
        motivo = f"Peixe salgado insuficiente (precisa de {regra['custo']})"
    elif estado["pescadores"] >= estado["limite"]:
        motivo = "Sem pescador livre"
    else:
        motivo = None

    if motivo:
        await recusar(sid, motivo, pedido)           # só quem pediu recebe
        return

    # pedido aceito: debita o custo, ocupa um pescador e abre a obra
    if regra["recurso"] == "peixe":
        consumir_peixe(regra["custo"])
    else:
        estado["salgado"] -= regra["custo"]
    estado["pescadores"] += 1
    obra_id = next(ids)
    vaga = vagas[tipo]
    vagas[tipo] += 1
    nome = jogadores[sid]["nome"]
    obras[obra_id] = {"tipo": tipo, "vaga": vaga, "por": nome, "fim": agora() + regra["tempo"]}

    # FATO para todos: a obra começou (causa: o pedido deste jogador)
    await sio.emit("construcao.iniciada",
                   fato(pedido, por=nome, tipo=tipo, obra=obra_id, vaga=vaga,
                        custo=regra["custo"], recurso=regra["recurso"]))
