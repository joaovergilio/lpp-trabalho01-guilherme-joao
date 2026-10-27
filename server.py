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
