from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedSection:
    title: str | None
    text: str
    page_number: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    mime_type: str
    sections: list[ParsedSection] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(
            section.text
            for section in self.sections
            if section.text.strip()
        )