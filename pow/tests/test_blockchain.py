import pytest
from blockchain import (
    DIFFICULTY,
    GENESIS_PREV,
    genesis,
    mine,
    new_block,
    validate_chain,
)


def test_genesis_is_the_same_on_every_node():
    a, b = genesis(), genesis()
    assert a.hash == b.hash
    assert a.previous_hash == GENESIS_PREV


def test_mine_meets_the_fixed_difficulty():
    g = genesis()
    b = mine(new_block([g], [{"sender": "ana", "to": "beto", "amount": 1}]))
    assert b.hash.startswith("0" * DIFFICULTY)
    assert b.hash == b.compute_hash()
    assert b.previous_hash == g.hash


def test_tampering_changes_the_hash():
    b = mine(new_block([genesis()], [{"amount": 1}]))
    b.transactions = [{"amount": 999}]
    assert b.compute_hash() != b.hash


@pytest.mark.skip(
    reason="TODO(TF): implement blockchain.validate_chain and enable this test"
)
def test_validate_chain_rejects_a_tampered_chain():
    g = genesis()
    b = mine(new_block([g], [{"amount": 1}]))
    assert validate_chain([g, b])[0]
    b.transactions = [{"amount": 999}]
    assert not validate_chain([g, b])[0]
