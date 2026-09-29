from packages.retrieval.evidence import Evidence


def build_context(
    evidence: list[Evidence],
) -> str:
    sections: list[str] = []

    for index, item in enumerate(evidence, start=1):
        source = item.document_title

        if item.section_title:
            source += f" — {item.section_title}"

        if item.page_number is not None:
            source += f" — page {item.page_number}"

        sections.append(
            f"[Source {index}]\n"
            f"Document: {source}\n"
            f"Chunk ID: {item.chunk_id}\n"
            f"Content:\n{item.text}"
        )

    return "\n\n".join(sections)