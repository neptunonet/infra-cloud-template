"""Mini proof-of-work blockchain: the BASELINE you extend into your TF.

What is already here (read it once, it is short):
  - Block: the data of one block and its sha256 hash.
  - genesis(): the first block, the same on every node.
  - mine(): the simplest PoW loop there is, with a FIXED difficulty.
  - new_block(): the next block on top of a chain.

What is NOT here: everything marked TODO(TF). That is your Trabajo Final:
a PoW blockchain of your own, with several nodes, running in the cloud.
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field

GENESIS_PREV = "0" * 64

# Leading hex zeros a block hash needs. FIXED on purpose: 3 zeros = about
# 4096 attempts, a few milliseconds on a laptop.
# TODO(TF): adjustable difficulty. Decide where it comes from (config, the
# chain itself, a retarget rule from the time between blocks...) and make
# every node agree on it.
DIFFICULTY = 3


@dataclass
class Block:
    index: int
    previous_hash: str
    transactions: list[dict]
    timestamp: float = field(default_factory=time.time)
    nonce: int = 0
    hash: str = ""

    def header(self) -> str:
        """Everything the hash covers except the nonce, as canonical JSON."""
        payload = {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "transactions": self.transactions,
            "timestamp": self.timestamp,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def compute_hash(self, nonce: int | None = None) -> str:
        n = self.nonce if nonce is None else nonce
        return hashlib.sha256(f"{self.header()}{n}".encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        return cls(**data)


def mine(block: Block) -> Block:
    """Try nonces 0, 1, 2, ... until the hash starts with DIFFICULTY zeros."""
    target = "0" * DIFFICULTY
    while True:
        h = block.compute_hash()
        if h.startswith(target):
            block.hash = h
            return block
        block.nonce += 1


def genesis() -> Block:
    """Block 0. Fixed timestamp, so every node computes the same genesis."""
    return mine(Block(0, GENESIS_PREV, [{"msg": "genesis infra-cloud"}], timestamp=0.0))


def new_block(chain: list[Block], transactions: list[dict]) -> Block:
    last = chain[-1]
    return Block(last.index + 1, last.hash, transactions)


def validate_chain(chain: list[Block]) -> tuple[bool, str]:
    """TODO(TF): validate a chain you RECEIVED from another node.

    Never trust a chain that arrived over the network. Think about: the
    genesis, the indexes, previous_hash links, recomputing every hash and the
    difficulty each block claims. Return (ok, reason).
    """
    raise NotImplementedError("TODO(TF): validate a received chain")


def choose_best_chain(candidates: list[list[Block]]) -> list[Block] | None:
    """TODO(TF): consensus. Among the VALID candidates (yours + your peers'),
    pick the one every node should keep: the longest valid chain (or the one
    with the most accumulated work). What happens on a tie?
    """
    raise NotImplementedError("TODO(TF): longest-valid-chain consensus")
