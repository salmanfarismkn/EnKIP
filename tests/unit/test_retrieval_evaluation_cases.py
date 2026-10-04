import json
from pathlib import Path


def test_retrieval_evaluation_case_ids_are_unique() -> None:
    cases_path = (
        Path(__file__).resolve().parents[1]
        / "evaluation"
        / "retrieval_cases.json"
    )
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    case_ids = [case["case_id"] for case in cases]

    assert len(case_ids) == len(set(case_ids))


def test_heldout_cases_are_separate_and_well_formed() -> None:
    evaluation_dir = Path(__file__).resolve().parents[1] / "evaluation"
    baseline_cases = json.loads(
        (evaluation_dir / "retrieval_cases.json").read_text(encoding="utf-8")
    )
    heldout_cases = json.loads(
        (evaluation_dir / "heldout_retrieval_cases.json").read_text(
            encoding="utf-8"
        )
    )

    from packages.retrieval.evaluation import validate_evaluation_cases

    baseline_ids = {case["case_id"] for case in baseline_cases}
    heldout_ids = [case["case_id"] for case in heldout_cases]

    assert len(heldout_cases) >= 8
    assert len(heldout_ids) == len(set(heldout_ids))
    assert baseline_ids.isdisjoint(heldout_ids)
    assert not validate_evaluation_cases(heldout_cases)
    assert all(
        set(case["expected_document_ids"]).isdisjoint(
            case.get("forbidden_document_ids", [])
        )
        for case in heldout_cases
    )
