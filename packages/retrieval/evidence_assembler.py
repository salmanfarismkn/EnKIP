from packages.retrieval.evidence import Evidence


class EvidenceAssembler:
    def assemble(
        self,
        results: list[dict],
        limit: int = 5,
    ) -> list[Evidence]:
        if limit <= 0:
            raise ValueError("Evidence limit must be positive")

        evidence: list[Evidence] = []

        for result in results[:limit]:
            evidence.append(
                Evidence(
                    chunk_id=result["chunk_id"],
                    document_id=result["document_id"],
                    document_title=result["document_title"],
                    text=result["text"],
                    section_title=result["section_title"],
                    page_number=result["page_number"],
                    retrieval_score=result["score"],
                    rerank_score=result["rerank_score"],
                )
            )

        return evidence