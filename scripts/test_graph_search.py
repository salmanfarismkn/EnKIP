from uuid import UUID

from sqlalchemy import select

from apps.api.config import settings
from packages.domain.database import SessionLocal
from packages.domain.models import User
from packages.retrieval.graph_search import GraphSearchService

tenant_id = UUID("1e36aa87-7d03-4195-8e2b-c49e6b9ffb08")

db = SessionLocal()

try:
    user_id = db.scalar(
        select(User.id)
        .where(User.tenant_id == tenant_id)
        .limit(1)
    )

    if user_id is None:
        print("No user exists for the test tenant; skipping graph search")
    else:
        service = GraphSearchService()

        results = service.search(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            query="Which team fixed the incident affecting the payment service?",
            limit=20,
        )

        print(f"RESULT COUNT: {len(results)}")

        for result in results:
            print("\n---")
            print("chunk:", result["chunk_id"])
            print("title:", result["document_title"])
            print("text:", result["text"])
            print("relationships:", result.get("graph_relationships"))

finally:
    db.close()