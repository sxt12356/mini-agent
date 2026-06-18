import re
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Section:
    heading_path: List[str]
    content_lines: List[str] = field(default_factory=list)

    @property
    def section_title(self) -> str:
        if not self.heading_path:
            return "未命名章节"
        return " / ".join(self.heading_path)

    @property
    def content(self) -> str:
        return "\n".join(self.content_lines).strip()


@dataclass
class Chunk:
    source: str
    section: str
    heading_path: List[str]
    chunk_index: int
    text: str

    @property
    def id(self) -> str:
        safe_section = self.section.replace("/", "-").replace(" ", "")
        return f"{self.source}#{safe_section}#chunk-{self.chunk_index}"

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source": self.source,
            "section": self.section,
            "heading_path": self.heading_path,
            "chunk_index": self.chunk_index,
            "text": self.text,
        }


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def normalize_text(text: str) -> str:
    """
    基础文本清洗。

    目标：
    1. 统一换行
    2. 去掉行尾空格
    3. 避免过多连续空行
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip() for line in text.split("\n")]
    cleaned = "\n".join(lines)

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def split_into_sections(text: str) -> List[Section]:
    """
    按 Markdown 标题切 section。

    支持：
    # 一级标题
    ## 二级标题
    ### 三级标题

    如果没有任何标题，则把第一行当作标题。
    """
    text = normalize_text(text)

    if not text:
        return []

    lines = text.split("\n")

    sections: List[Section] = []
    current_section: Section | None = None
    heading_stack: List[str] = []

    found_heading = False

    for line in lines:
        match = HEADING_PATTERN.match(line.strip())

        if match:
            found_heading = True

            level = len(match.group(1))
            title = match.group(2).strip()

            heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)

            if current_section and current_section.content:
                sections.append(current_section)

            current_section = Section(
                heading_path=heading_stack.copy(),
                content_lines=[],
            )
            continue

        if current_section is None:
            current_section = Section(
                heading_path=["文档"],
                content_lines=[],
            )

        current_section.content_lines.append(line)

    if current_section and current_section.content:
        sections.append(current_section)

    if found_heading:
        return sections

    # 没有 Markdown 标题时，使用第一行作为标题。
    non_empty_lines = [line.strip() for line in lines if line.strip()]

    if not non_empty_lines:
        return []

    title = non_empty_lines[0]
    body = "\n".join(non_empty_lines[1:]).strip()

    if not body:
        body = title

    return [
        Section(
            heading_path=[title],
            content_lines=body.split("\n"),
        )
    ]


def split_paragraphs(text: str) -> List[str]:
    """
    按段落切分。

    规则：
    1. 空行分段
    2. 如果没有空行，则按非空行分段
    """
    text = normalize_text(text)

    if "\n\n" in text:
        paragraphs = [
            p.strip()
            for p in text.split("\n\n")
            if p.strip()
        ]
    else:
        paragraphs = [
            line.strip()
            for line in text.split("\n")
            if line.strip()
        ]

    return paragraphs


def hard_split_text(
    text: str,
    max_chars: int,
    overlap_chars: int,
) -> List[str]:
    """
    兜底切分。

    当某个段落特别长时，用固定长度切开。
    """
    chunks = []
    start = 0

    while start < len(text):
        end = start + max_chars
        piece = text[start:end].strip()

        if piece:
            chunks.append(piece)

        if end >= len(text):
            break

        start = max(end - overlap_chars, start + 1)

    return chunks


def pack_paragraphs(
    paragraphs: List[str],
    *,
    max_chars: int,
    overlap_paragraphs: int = 1,
) -> List[str]:
    """
    把多个段落打包成 chunk。

    思路：
    - 尽量让 chunk 不超过 max_chars
    - chunk 之间保留最后 N 个段落作为 overlap
    """
    chunks: List[str] = []
    current: List[str] = []

    for paragraph in paragraphs:
        candidate = "\n".join(current + [paragraph]).strip()

        if len(candidate) <= max_chars:
            current.append(paragraph)
            continue

        if current:
            chunks.append("\n".join(current).strip())

            if overlap_paragraphs > 0:
                current = current[-overlap_paragraphs:]
            else:
                current = []
        else:
            current = []

        if len(paragraph) > max_chars:
            chunks.extend(
                hard_split_text(
                    paragraph,
                    max_chars=max_chars,
                    overlap_chars=max_chars // 5,
                )
            )
            current = []
        else:
            current.append(paragraph)

    if current:
        chunks.append("\n".join(current).strip())

    return chunks


def build_chunks_for_document(
    *,
    source: str,
    text: str,
    max_chars: int = 800,
    overlap_paragraphs: int = 1,
) -> List[Chunk]:
    """
    文档 → sections → chunks。

    每个 chunk 都带：
    - source
    - section
    - heading_path
    - chunk_index
    - text
    """
    sections = split_into_sections(text)
    chunks: List[Chunk] = []

    chunk_index = 0

    for section in sections:
        section_title = section.section_title
        paragraphs = split_paragraphs(section.content)

        if not paragraphs:
            continue

        packed = pack_paragraphs(
            paragraphs,
            max_chars=max_chars,
            overlap_paragraphs=overlap_paragraphs,
        )

        for body in packed:
            # 关键：chunk text 里带上 heading，提升检索语义。
            chunk_text = f"{section_title}\n\n{body}".strip()

            chunks.append(
                Chunk(
                    source=source,
                    section=section_title,
                    heading_path=section.heading_path,
                    chunk_index=chunk_index,
                    text=chunk_text,
                )
            )

            chunk_index += 1

    return chunks