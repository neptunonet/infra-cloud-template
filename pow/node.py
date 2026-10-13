"""HTTP node of the mini PoW blockchain: the BASELINE you extend into your TF.

It runs as ONE node and already answers the contract the course uses
(port 8090, the same paths the chart, the ServiceMonitor and the docs expect):
  - GET  /healthz   -> {"status": "ok"}
  - GET  /metrics   -> Prometheus, with pow_block_height
  - GET  /chain     -> the local chain, as JSON
  - GET  /tx        -> the pending transactions
  - POST /tx        -> {"sender": "ana", "to": "beto", "amount": 1}
  - POST /mine      -> mine one block with the pending transactions

The chain is a JSON file under DATA_DIR (default /data): kill the container,
keep the disk, keep the chain.

TODO(TF), none of this is implemented. It is your Trabajo Final:
  - Peers: PEERS (comma-separated URLs, the chart fills it in) is read below
    but not used. Add GET /peers and POST /peers/sync: fetch the peers'
    chains, validate them (blockchain.validate_chain) and keep the best one
    (blockchain.choose_best_chain). Should a new block also be pushed to the
    peers instead of waiting for a sync?
  - Adjustable difficulty (blockchain.DIFFICULTY is a constant).
  - Mempool rules: today ANY transaction is accepted (negative amounts,
    duplicates, no signature, no balance check). Define what is valid.
  - Concurrency: FastAPI runs these endpoints in a thread pool. Two /mine at
    once, or a /tx while mining, can lose blocks or transactions, and
    chain.json is not written atomically. Make it safe.
  - More metrics for your dashboard (peers, mining time, ...).
"""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from blockchain import Block, genesis, mine, new_block
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
CHAIN_FILE = DATA_DIR / "chain.json"
PORT = int(os.environ.get("PORT", "8090"))
# TODO(TF): use them (GET /peers, POST /peers/sync). Read here so the chart's
# PEERS value already reaches the process.
PEERS = [p.strip() for p in os.environ.get("PEERS", "").split(",") if p.strip()]

BLOCK_HEIGHT = Gauge("pow_block_height", "Height of the local chain (last block index)")

# TODO(TF): mempool rules and concurrency safety (see the module docstring).
pending_tx: list[dict[str, Any]] = []


class Tx(BaseModel):
    sender: str
    to: str
    amount: float


def load_chain() -> list[Block]:
    if CHAIN_FILE.exists():
        return [Block.from_dict(b) for b in json.loads(CHAIN_FILE.read_text())]
    chain = [genesis()]
    save_chain(chain)
    return chain


def save_chain(chain: list[Block]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHAIN_FILE.write_text(json.dumps([b.to_dict() for b in chain]))


@asynccontextmanager
async def lifespan(_: FastAPI):
    BLOCK_HEIGHT.set(load_chain()[-1].index)
    yield


app = FastAPI(title="pow-node-baseline", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/chain")
def get_chain() -> list[dict[str, Any]]:
    return [b.to_dict() for b in load_chain()]


@app.get("/tx")
def get_pending_tx() -> list[dict[str, Any]]:
    return pending_tx


@app.post("/tx", status_code=201)
def add_tx(tx: Tx) -> dict[str, Any]:
    entry = tx.model_dump() | {"received_at": time.time()}
    pending_tx.append(entry)  # TODO(TF): validate before accepting
    return entry


@app.post("/mine")
def mine_block() -> dict[str, Any]:
    chain = load_chain()
    block = mine(new_block(chain, list(pending_tx) or [{"msg": "empty block"}]))
    pending_tx.clear()
    chain.append(block)
    save_chain(chain)
    BLOCK_HEIGHT.set(block.index)
    return {"mined": block.to_dict()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
