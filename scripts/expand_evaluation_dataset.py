
import json
from pathlib import Path

EVALUATION_FILE = Path("tests/evaluation/retrieval_cases.json")

TENANT_ID = "9c0340ca-571b-4928-a0a6-a13de3b089eb"
USER_ID = "72154ff0-9af7-4a91-9522-e63b5b9de18e"

new_cases = [
    {
        "case_id": "platform-001",
        "query": "Which database is the system's source of record, and how is semantic retrieval implemented?",
        "document_id": "b9f81518-a727-42e0-8806-a079102a2918",
    },
    {
        "case_id": "platform-002",
        "query": "How does the search architecture combine lexical and vector results?",
        "document_id": "b9f81518-a727-42e0-8806-a079102a2918",
    },
    {
        "case_id": "platform-003",
        "query": "What authentication and authorization controls are required before users can access knowledge?",
        "document_id": "90d8d21d-c6e3-48bf-8334-24e1e25107a5",
    },
    {
        "case_id": "platform-004",
        "query": "How should access to individual data sources be controlled and audited?",
        "document_id": "90d8d21d-c6e3-48bf-8334-24e1e25107a5",
    },
    {
        "case_id": "platform-005",
        "query": "Why might uploaded documents remain unavailable in search?",
        "document_id": "7fa88f93-bca7-4652-b207-4f9de18f10d1",
    },
    {
        "case_id": "platform-006",
        "query": "Which operational signals help diagnose an ingestion backlog?",
        "document_id": "7fa88f93-bca7-4652-b207-4f9de18f10d1",
    },
    {
        "case_id": "platform-007",
        "query": "Which retrieval metrics should be used to evaluate search quality?",
        "document_id": "90fe91db-8e03-47a9-ba4c-9a997dd707e6",
    },
    {
        "case_id": "platform-008",
        "query": "What testing and operational improvements are planned for the next search roadmap?",
        "document_id": "90fe91db-8e03-47a9-ba4c-9a997dd707e6",
    },
    {
        "case_id": "platform-009",
        "query": "How far in advance should employees request equipment, and who approves the request?",
        "document_id": "1d99f991-6b60-44a0-bf26-fcfc75d0ae2f",
    },
    {
        "case_id": "platform-010",
        "query": "What steps are required for account setup and access to internal knowledge sources?",
        "document_id": "1d99f991-6b60-44a0-bf26-fcfc75d0ae2f",
    },
    {
        "case_id": "platform-011",
        "query": "How frequently are backups performed and restore tests conducted?",
        "document_id": "30b660c3-925e-4ff1-a63e-dbbf4702a9fd",
    },
    {
        "case_id": "platform-012",
        "query": "What must be removed when a data source is deleted, and what are the recovery targets?",
        "document_id": "30b660c3-925e-4ff1-a63e-dbbf4702a9fd",
    },
]

cases = json.loads(EVALUATION_FILE.read_text(encoding="utf-8"))
existing_ids = {case["case_id"] for case in cases}

added = 0

for item in new_cases:
    if item["case_id"] in existing_ids:
        continue

    cases.append({
        "case_id": item["case_id"],
        "tenant_id": TENANT_ID,
        "user_id": USER_ID,
        "query": item["query"],
        "expected_document_ids": [item["document_id"]],
    })
    existing_ids.add(item["case_id"])
    added += 1

EVALUATION_FILE.write_text(
    json.dumps(cases, indent=2) + "\n",
    encoding="utf-8",
)

print(f"Added {added} evaluation cases.")
print(f"Total evaluation cases: {len(cases)}")