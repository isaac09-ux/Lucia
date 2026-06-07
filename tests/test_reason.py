import json
import pytest
from lucia.reason import compute_facts, build_messages

def test_compute_facts_empty():
    assert compute_facts([]) is None

def test_compute_facts_single_match():
    history = [
        {"jersey": 10, "player_name": "Ana", "distance_m": 1000, "avg_speed_m_per_s": 1.5, "dominant_zone": "A5"}
    ]
    facts = compute_facts(history)
    assert facts is not None
    assert facts["n_matches"] == 1
    assert len(facts["flags"]) == 0

def test_compute_facts_distance_drops():
    history = [
        {"jersey": 10, "distance_m": 1200},
        {"jersey": 10, "distance_m": 1100},
        {"jersey": 10, "distance_m": 1000},
    ]
    facts = compute_facts(history)
    assert any("distancia recorrida baja 3+ partidos seguidos" in f for f in facts["flags"])

def test_compute_facts_speed_rises():
    history = [
        {"jersey": 10, "avg_speed_m_per_s": 1.2},
        {"jersey": 10, "avg_speed_m_per_s": 1.4},
        {"jersey": 10, "avg_speed_m_per_s": 1.6},
    ]
    facts = compute_facts(history)
    assert any("velocidad media sube 3+ partidos" in f for f in facts["flags"])

def test_zone_consistency_perfect():
    history = [
        {"jersey": 10, "dominant_zone": "A5"},
        {"jersey": 10, "dominant_zone": "A5"},
    ]
    facts = compute_facts(history)
    assert facts["spatial"]["zone_consistency"] == 1.0

def test_zone_consistency_instability_flag():
    history = [
        {"jersey": 10, "dominant_zone": "A5"},
        {"jersey": 10, "dominant_zone": "A1"},
        {"jersey": 10, "dominant_zone": "A3"},
    ]
    facts = compute_facts(history)
    assert facts["spatial"]["zone_consistency"] < 0.5
    assert any("zona dominante inestable" in f for f in facts["flags"])

def test_court_pos_drift():
    history = [
        {"jersey": 10, "avg_court_pos_m": "[0.0, 0.0]"},
        {"jersey": 10, "avg_court_pos_m": "[3.0, 4.0]"},
    ]
    facts = compute_facts(history)
    assert facts["spatial"]["court_pos_drift_m"] == 5.0

def test_high_touch_load_flag():
    history = [
        {"jersey": 10, "touch_rallies": 2.0},
        {"jersey": 10, "touch_rallies": 3.0},
        {"jersey": 10, "touch_rallies": 4.0},
    ]
    facts = compute_facts(history)
    assert any("carga de toques alta" in f for f in facts["flags"])

def test_reliability_warning_flag():
    history = [
        {"jersey": 10, "reliability": "alta"},
        {"jersey": 10, "reliability": "baja"},
    ]
    facts = compute_facts(history)
    assert any("fiabilidad de tracking BAJA" in f for f in facts["flags"])

def test_semantic_notes_empty():
    history = [
        {"jersey": 10, "clara_reason_notes": None},
    ]
    facts = compute_facts(history)
    assert facts["semantic_notes"] == []

def test_build_messages_with_semantic_notes():
    facts = {
        "semantic_notes": ["Nota de prueba 1", "Nota de prueba 2"]
    }
    messages = build_messages(facts)
    user_content = messages[1]["content"]
    assert "NOTAS SEMÁNTICAS" in user_content
    assert "Nota de prueba 1" in user_content
