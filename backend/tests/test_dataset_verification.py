from app.crypto import fdr_number_hash
from app.demo_dataset import seed_demonstration_dataset
from app.models import Deposit, Institution, IntegrityFinding, RegulationRule, ReleaseRequest, FDRLineageRelation, FDRLifecycleEvent, AssessmentSnapshot
from app.services import trace_service, readiness_service, regulation_service, integrity_service

def test_demonstration_dataset_integrity(client, db):
    # client fixture drops and creates tables, then calls seed_demo_users
    # Let's ensure seed_demonstration_dataset is run
    seed_demonstration_dataset(db)

    # 1. Lineage check for DIT-105
    dit_105 = db.query(Deposit).filter_by(reference_hash=fdr_number_hash("DEMO-FDR-DIT-105")).first()
    assert dit_105 is not None
    lineage = trace_service.get_fdr_lineage_graph(db, dit_105.id)
    assert lineage["total_nodes"] == 3
    assert lineage["total_edges"] == 2

    # Tamper check for all demo deposits
    all_demo = [d for d in db.query(Deposit).all() if d.reference_no.startswith("DEMO")]  # numbers are encrypted, so filter in Python
    assert len(all_demo) >= 35
    for d in all_demo:
        events = trace_service.get_fdr_timeline(db, d.id)
        assert events["integrity"]["valid"] is True, f"Tamper failure on {d.reference_no}"

    # 2. Release Readiness: CTU-401 (Fully satisfied)
    ctu_401 = db.query(Deposit).filter_by(reference_hash=fdr_number_hash("DEMO-FDR-CTU-401")).first()
    res_ctu = readiness_service.evaluate_release_readiness(db, ctu_401.id)
    assert res_ctu["overall_status"] == "READY_FOR_APPROVAL"
    assert res_ctu["is_ready_for_decision"] is True

    # RIE-601 (Blocked by missing documents)
    rie_601 = db.query(Deposit).filter_by(reference_hash=fdr_number_hash("DEMO-FDR-RIE-601")).first()
    res_rie = readiness_service.evaluate_release_readiness(db, rie_601.id)
    assert res_rie["overall_status"] in ("BLOCKED", "INCOMPLETE")
    assert any("Document" in b for b in res_rie["blocking_reasons"])

    # HPI-701 (Blocked by term incomplete)
    hpi_701 = db.query(Deposit).filter_by(reference_hash=fdr_number_hash("DEMO-FDR-HPI-701")).first()
    res_hpi = readiness_service.evaluate_release_readiness(db, hpi_701.id)
    assert res_hpi["overall_status"] == "BLOCKED"
    assert any("Maturity" in b or "term" in b.lower() for b in res_hpi["blocking_reasons"])

    # CICT-501 (Blocked by active integrity anomaly)
    cict_501 = db.query(Deposit).filter_by(reference_hash=fdr_number_hash("DEMO-FDR-CICT-501")).first()
    res_cict = readiness_service.evaluate_release_readiness(db, cict_501.id)
    assert res_cict["overall_status"] == "BLOCKED"
    assert any("Integrity" in b or "anomaly" in b.lower() for b in res_cict["blocking_reasons"])

    # DIT-106 (Blocked by discrepancy)
    dit_106 = db.query(Deposit).filter_by(reference_hash=fdr_number_hash("DEMO-FDR-DIT-106")).first()
    res_dit106 = readiness_service.evaluate_release_readiness(db, dit_106.id)
    assert res_dit106["overall_status"] == "BLOCKED"
    assert any("Consistency" in b or "discrepanc" in b.lower() for b in res_dit106["blocking_reasons"])

    # 3. Regulation Replay
    sias_303 = db.query(Deposit).filter_by(reference_hash=fdr_number_hash("DEMO-FDR-SIAS-303")).first()
    rule_2020 = db.query(RegulationRule).filter_by(rule_code="REG-AICTE-APH-2020", version="1.0.0").first()
    rule_2025 = db.query(RegulationRule).filter_by(rule_code="REG-AICTE-APH-2025", version="2.5.0-DEMO").first()
    assert rule_2020 is not None and rule_2025 is not None

    snap_303 = db.query(AssessmentSnapshot).filter_by(deposit_id=sias_303.id, rule_id=rule_2020.id).first()
    assert snap_303 is not None
    assert snap_303.evaluation_result == "COMPLIANT"

    replay_res = regulation_service.replay_and_compare(db, sias_303.id, rule_2025.id, assessed_by="test_verifier")
    assert replay_res["earlier_assessment"]["evaluation_result"] == "COMPLIANT"
    assert replay_res["replay_assessment"]["evaluation_result"] == "NON_COMPLIANT"
    assert len(replay_res["newly_identified_issues"]) > 0

    # 4. Cross-Record Integrity Network
    findings = db.query(IntegrityFinding).all()
    categories = {f.category for f in findings}
    assert "NORMALIZED_DUPLICATE" in categories
    assert "AMOUNT_DATE_CONFLICT" in categories
    assert "INCONSISTENT_BANK_INSTITUTION" in categories
    assert "INVALID_PREDECESSOR_LINK" in categories
    assert "MULTIPLE_ACTIVE_DEPOSITS" in categories
    assert "SUPERSEDED_RELEASE_LINK" in categories

    net_graph = integrity_service.get_integrity_network_graph(db)
    assert len(net_graph["nodes"]) > 0
    assert len(net_graph["edges"]) > 0
