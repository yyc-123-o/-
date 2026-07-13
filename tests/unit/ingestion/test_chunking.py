from skillforge_kb.ingestion.chunking import PedagogicalChunker


def test_definition_heading_stays_with_definition_body() -> None:
    text = (
        "## Definition\nLogistic regression estimates conditional class probability "
        "with a sigmoid applied to a linear combination of input features.\n"
        "## Example\nUse the sigmoid output as the positive-class probability "
        "in binary classification."
    )
    chunks = PedagogicalChunker(chunk_size=180, overlap=20).split(text)
    assert chunks[0].startswith("## Definition")
    assert "estimates conditional class probability" in chunks[0]


def test_markdown_headings_define_chunk_boundaries() -> None:
    definition = "D" * 90
    example = "E" * 90
    text = f"## Definition\n{definition}\n## Example\n{example}"

    chunks = PedagogicalChunker(chunk_size=180, overlap=20).split(text)

    assert chunks == [f"## Definition\n{definition}", f"## Example\n{example}"]


def test_paragraph_boundaries_are_preferred_when_section_exceeds_chunk_size() -> None:
    first_paragraph = "A" * 90
    second_paragraph = "B" * 90

    chunks = PedagogicalChunker(chunk_size=120, overlap=20).split(
        f"{first_paragraph}\n\n{second_paragraph}"
    )

    assert chunks == [first_paragraph, second_paragraph]


def test_short_fenced_code_block_is_preserved_whole() -> None:
    code = "```python\n" + "\n".join(f"value_{index} = {index}" for index in range(12)) + "\n```"
    assert len(code) > 100

    chunks = PedagogicalChunker(chunk_size=100, overlap=20).split(code)

    assert chunks == [code]
