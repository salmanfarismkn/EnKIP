from sentence_transformers import CrossEncoder


class LocalCrossEncoderReranker:
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ) -> None:
        self._model_name = model_name
        self._model = CrossEncoder(model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    def rerank(
        self,
        query: str,
        results: list[dict],
    ) -> list[dict]:
        if not query.strip():
            raise ValueError("Query must not be empty")

        if not results:
            return []

        pairs = [
            [query, result["text"]]
            for result in results
        ]

        scores = self._model.predict(
            pairs,
            show_progress_bar=False,
        )

        reranked = []

        for result, score in zip(
            results,
            scores,
            strict=True,
        ):
            updated = dict(result)
            updated["rerank_score"] = float(score)
            reranked.append(updated)

        reranked.sort(
            key=lambda result: result["rerank_score"],
            reverse=True,
        )

        return reranked