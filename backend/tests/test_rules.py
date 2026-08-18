from app.services.match import MatchProvider, MockMatchProvider
from app.services.rules import (
    DemandRules,
    ResourcePassportInput,
    RuleCheck,
    evaluate_rules,
)


def test_explicit_rule_failure_has_priority_over_missing_information() -> None:
    result = RuleCheck(
        quantity=False,
        required_info=False,
        location=None,
        missing_fields=("composition",),
    )

    assert result.status == "RULE_FAIL"


def test_missing_required_information_needs_info() -> None:
    result = evaluate_rules(
        ResourcePassportInput(
            passport_id="PASSPORT-DEMO-MISSING",
            description="실리콘계 분말",
            quantity=12,
            unit="kg",
        ),
        DemandRules(required_fields=("description", "composition")),
    )

    assert result.required_info is False
    assert result.missing_fields == ("composition",)
    assert result.status == "NEEDS_INFO"


def test_optional_unassessed_location_stays_reviewable_and_is_labelled() -> None:
    # Golden D01 contract: an unconfigured location rule is null/미평가, not
    # automatically NEEDS_INFO.
    result = RuleCheck(
        quantity=True,
        required_info=True,
        location=None,
        missing_fields=(),
    )

    assert result.status == "REVIEW"
    assert result.display_labels()["location"] == "미평가"


def test_configured_but_missing_location_needs_information() -> None:
    result = evaluate_rules(
        ResourcePassportInput(
            passport_id="PASSPORT-DEMO-NO-LOCATION",
            description="실리콘계 분말",
        ),
        DemandRules(
            accepted_locations=("경상북도",),
            required_fields=("description",),
        ),
    )

    assert result.location is None
    assert result.missing_fields == ("location",)
    assert result.status == "NEEDS_INFO"


def test_mock_provider_returns_deterministic_contract_safe_top3() -> None:
    provider = MockMatchProvider()
    passport = ResourcePassportInput(
        passport_id="PASSPORT-DEMO-GOLDEN",
        description="반도체 세정 공정에서 회수된 무기질 분말",
        quantity=12,
        unit="kg",
        condition=None,
        location="경상북도 포항시",
        composition="실리콘 95%, 기타 무기물 5%",
    )

    first = provider.match(passport)
    second = provider.match(passport)

    assert isinstance(provider, MatchProvider)
    assert first == second
    assert first.model == "Xenova/bge-m3"
    assert first.source_type == "DEMO"
    assert len(first.candidates) == 3
    assert [candidate.rank for candidate in first.candidates] == [1, 2, 3]
    assert [candidate.status for candidate in first.candidates] == [
        "REVIEW",
        "NEEDS_INFO",
        "NEEDS_INFO",
    ]

    golden = first.candidates[0]
    assert golden.demand_id == "D01"
    assert golden.semantic_similarity == 0.649156
    assert golden.rule_check.quantity is True
    assert golden.rule_check.required_info is True
    assert golden.rule_check.location is None
    assert golden.rule_check.missing_fields == ()
    assert golden.status == "REVIEW"

    payload = first.as_dict()
    assert payload["candidates"][0]["rule_check"]["location"] is None
    assert payload["candidates"][0]["status"] == "REVIEW"


def test_mock_provider_rejects_unsupported_top_k() -> None:
    provider = MockMatchProvider()
    passport = ResourcePassportInput(passport_id="PASSPORT-DEMO-001")

    for top_k in (0, 4):
        try:
            provider.match(passport, top_k=top_k)
        except ValueError as error:
            assert "top_k" in str(error)
        else:
            raise AssertionError("unsupported top_k must raise ValueError")


def test_mock_provider_rejects_an_unrelated_passport() -> None:
    provider = MockMatchProvider()
    unrelated = ResourcePassportInput(
        passport_id="PASSPORT-DEMO-ALUMINUM",
        description="알루미늄 절삭 스크랩",
        quantity=12,
        unit="kg",
    )

    try:
        provider.match(unrelated)
    except ValueError as error:
        assert "Golden R01" in str(error)
    else:
        raise AssertionError("frozen R01 scores must not be reused for unrelated input")
