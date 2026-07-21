from reachpath.strategy import generate_strategies


def test_strategy_is_honest_when_no_relationships_or_contacts_exist() -> None:
    strategy = generate_strategies(
        {"person": "Nadia Karim", "company": "Example Labs", "objective": "Obtenir un rendez-vous"},
        {"subject": {"name": "Nadia Karim"}, "evidence": [], "relationships": []},
    )
    assert len(strategy["scenarios"]) == 3
    assert strategy["human_review_required"] is True
    assert all(scenario["requires_validation"] for scenario in strategy["scenarios"])
    assert strategy["limitations"]
