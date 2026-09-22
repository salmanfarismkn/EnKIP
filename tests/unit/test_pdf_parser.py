from packages.ingestion.parser_registry import ParserRegistry


def test_pdf_parser_is_selected() -> None:
    registry = ParserRegistry()

    parser = registry.get_parser(
        "application/pdf"
    )

    assert parser.__class__.__name__ == "PdfParser"