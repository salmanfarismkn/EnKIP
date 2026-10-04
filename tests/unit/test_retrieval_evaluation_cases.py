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
