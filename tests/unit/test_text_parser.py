from packages.ingestion.text_parser import TextParser


def test_text_parser() -> None:
    parser = TextParser()

    result = parser.parse(
        b"Enterprise knowledge platform",
        "test.txt",
    )

    assert result.title == "test.txt"
    assert result.text == "Enterprise knowledge platform"
    assert len(result.sections) == 1