from common.serializers.json_serializer import JsonSerializer
from common.serializers.serialization import domain_state_serializer
from ledger.ledger import Ledger
from plenum.common.constants import CURRENT_PROTOCOL_VERSION
from plenum.common.txn_util import do_req_to_txn
from plenum.server.batch_handlers.three_pc_batch import ThreePcBatch

DEFAULT_PRIMARIES = ['Alpha', 'Beta']

def check_audit_ledger_updated(audit_size_initial, nodes, audit_txns_added):
    audit_size_after = [node.auditLedger.size for node in nodes]
    for i in range(len(nodes)):
        assert audit_size_after[i] == audit_size_initial[i] + audit_txns_added, \
            "{} != {}".format(audit_size_after[i], audit_size_initial[i] + audit_txns_added)


def check_audit_txn(txn,
                    view_no, pp_seq_no,
                    seq_no, txn_time,
                    ledger_id, txn_root, state_root,
                    pool_size, domain_size, config_size,
                    last_domain_seqno, last_pool_seqno, last_config_seqno,
                    primaries):
    expectedLedgerRoots = {}
    # we expect deltas here, that is a difference from the current audit ledger txn to
    # the audit txn where the corresponding ledger was updated
    if last_domain_seqno:
        expectedLedgerRoots[1] = seq_no - last_domain_seqno
    if last_pool_seqno:
        expectedLedgerRoots[0] = seq_no - last_pool_seqno
    if last_config_seqno:
        expectedLedgerRoots[2] = seq_no - last_config_seqno
    expectedLedgerRoots[ledger_id] = Ledger.hashToStr(txn_root)

    expected = {
        "reqSignature": {},
        "txn": {
            "data": {
                "ledgerRoot": expectedLedgerRoots,
                "ver": "1",
                "viewNo": view_no,
                "ppSeqNo": pp_seq_no,
                "ledgerSize": {
                    0: pool_size,
                    1: domain_size,
                    2: config_size
                },
                "stateRoot": {
                    ledger_id: Ledger.hashToStr(state_root),
                },
                "primaries": primaries

            },
            "metadata": {
            },
            "protocolVersion": CURRENT_PROTOCOL_VERSION,
            "type": "2",  # AUDIT
        },
        "txnMetadata": {
            "seqNo": seq_no,
            "txnTime": txn_time
        },

        "ver": "1"
    }
    txn = JsonSerializer().serialize(txn)
    expected = JsonSerializer().serialize(expected)
    print(txn)
    print(expected)
    assert expected == txn


def do_apply_audit_txn(alh,
                       txns_count, ledger_id,
                       view_no, pp_sq_no, txn_time,
                       has_audit_txn=True):
    db_manager = alh.database_manager
    add_txns(db_manager, ledger_id, txns_count, txn_time)
    three_pc_batch = ThreePcBatch(ledger_id=ledger_id,
                                  inst_id=0,
                                  view_no=view_no,
                                  pp_seq_no=pp_sq_no,
                                  pp_time=txn_time,
                                  state_root=db_manager.get_state(ledger_id).headHash,
                                  txn_root=db_manager.get_ledger(ledger_id).uncommitted_root_hash,
                                  primaries=DEFAULT_PRIMARIES,
                                  valid_digests=[],
                                  has_audit_txn=has_audit_txn)
    alh.post_batch_applied(three_pc_batch)


def add_txns(db_manager, ledger_id, count, txn_time):
    ledger = db_manager.get_ledger(ledger_id)
    state = db_manager.get_state(ledger_id)

    txns = [do_req_to_txn({}, {"ledger_id": ledger_id, "num": i}) for i in range(count)]
    ledger.append_txns_metadata(txns, txn_time)

    ledger.appendTxns(txns)
    for i, txn in enumerate(txns):
        state.set(bytes(ledger_id + i),
                  domain_state_serializer.serialize(txn))
