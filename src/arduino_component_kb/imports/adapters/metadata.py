"""Small HTML metadata collector shared by explicit source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True, slots=True)
class MetadataSnapshot:
    canonical_urls: tuple[str, ...]
    descriptions: tuple[str, ...]
    titles: tuple[str, ...]


class MetadataCollector(HTMLParser):
    """Collect only explicitly selected metadata; never retain remote HTML."""

    def __init__(self, *, title_class: str) -> None:
        super().__init__(convert_charrefs=True)
        self.title_class = title_class
        self.canonical_urls: list[str] = []
        self.descriptions: list[str] = []
        self.title_blocks: list[list[str]] = []
        self._title_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value for name, value in attrs}
        classes = frozenset((attributes.get("class") or "").split())
        rel = frozenset((attributes.get("rel") or "").casefold().split())
        if tag.casefold() == "link" and "canonical" in rel:
            href = attributes.get("href")
            if href is not None:
                self.canonical_urls.append(href)
        elif (
            tag.casefold() == "meta" and (attributes.get("name") or "").casefold() == "description"
        ):
            content = attributes.get("content")
            if content is not None:
                self.descriptions.append(content)
        if tag.casefold() == "h1" and self.title_class in classes:
            self.title_blocks.append([])
            self._title_depth = 1
        elif self._title_depth:
            self._title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._title_depth:
            self._title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self.title_blocks[-1].append(data)

    def snapshot(self) -> MetadataSnapshot:
        return MetadataSnapshot(
            canonical_urls=tuple(self.canonical_urls),
            descriptions=tuple(self.descriptions),
            titles=tuple(" ".join(parts) for parts in self.title_blocks),
        )


def collect_metadata(html: str, *, title_class: str) -> MetadataSnapshot:
    collector = MetadataCollector(title_class=title_class)
    collector.feed(html)
    return collector.snapshot()
