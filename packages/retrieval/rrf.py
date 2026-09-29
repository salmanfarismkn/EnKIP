from dataclasses import dataclass
from uuid import UUID


@dataclass
class RankedResult:
    chunk_id: UUID
    score: float
    result: dict


class ReciprocalRankFusion:
    def __init__(self, k: int = 60) -> None:
        if k <= 0:
            raise ValueError("RRF k must be positive")

        self._k = k

    def fuse(
        self,
        result_lists: list[list[dict]],
    ) -> list[dict]:
        scores: dict[UUID, float] = {}
        results_by_id: dict[UUID, dict] = {}

        for results in result_lists:
            for rank, result in enumerate(results, start=1):
                chunk_id = result["chunk_id"]

                scores[chunk_id] = (
                    scores.get(chunk_id, 0.0)
                    + 1.0 / (self._k + rank)
                )

                results_by_id[chunk_id] = result

        ranked = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        fused_results = []

        for chunk_id, score in ranked:
            result = dict(results_by_id[chunk_id])
            result["score"] = score
            fused_results.append(result)

        return fused_results