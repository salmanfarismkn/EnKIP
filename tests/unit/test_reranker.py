from packages.retrieval.reranker import Reranker


class FakeReranker:
    model_name = "fake-reranker"

    def rerank(
        self,
        query: str,
        results: list[dict],
    ) -> list[dict]:
        ranked = []

        for index, result in enumerate(
            results,
            start=1,
        ):
            updated = dict(result)
            updated["rerank_score"] = 1.0 / index
            ranked.append(updated)

        return ranked