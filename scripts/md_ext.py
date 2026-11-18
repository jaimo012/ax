"""Python-Markdown 확장: 수식 블록과 그림(figure·figcaption).

- 수식: ```formula 코드펜스 → <div class="formula"><code>…</code></div> (인용구와 구분되는 수식 전용 블록)
- 그림: 문단에 이미지 하나만 있으면 <figure> 로 감싸고 title 을 <figcaption> 으로 쓴다.
        src 가 figures/ 로 시작하면 사이트 경로(/ax/figures/…)로 바꾼다.
        alt 가 비어 있으면 실패한다 — AI 가 그림 내용을 읽는 통로가 alt 다.
새 패키지 없이 Python-Markdown 기본 API 만 쓴다.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor

FORMULA_FENCE = re.compile(r"^```formula[ \t]*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)
FIGURES_PREFIX: str = "figures/"
# fenced_code(25) 보다 먼저 돌아야 ```formula 를 일반 코드블록으로 가져가지 않는다
FORMULA_PRIORITY: int = 30
FIGURE_PRIORITY: int = 5


class MarkdownContentError(ValueError):
    """원고 안의 그림·수식 문법 오류 (빌드에서 파일명과 함께 보고)."""


class FormulaPreprocessor(Preprocessor):
    def run(self, lines: list[str]) -> list[str]:
        text = "\n".join(lines)

        def to_block(match: re.Match) -> str:
            body = html.escape(match.group(1).strip())
            return "\n" + self.md.htmlStash.store(f'<div class="formula"><code>{body}</code></div>') + "\n"

        return FORMULA_FENCE.sub(to_block, text).split("\n")


class FigureTreeprocessor(Treeprocessor):
    def __init__(self, md: Markdown, base_path: str) -> None:
        super().__init__(md)
        self.base_path = base_path

    def fix_image(self, img: etree.Element) -> None:
        src = img.get("src", "")
        if not img.get("alt", "").strip():
            raise MarkdownContentError(f"대체텍스트(alt)가 빈 이미지: {src or '(src 없음)'}")
        if src.startswith(FIGURES_PREFIX):
            img.set("src", self.base_path + src)
        img.set("loading", "lazy")
        img.set("decoding", "async")

    def run(self, root: etree.Element) -> None:
        for img in root.iter("img"):
            self.fix_image(img)
        for parent in root.iter():
            for index, child in enumerate(list(parent)):
                only_image = (child.tag == "p" and len(child) == 1 and child[0].tag == "img"
                              and not (child.text or "").strip() and not (child[0].tail or "").strip())
                if not only_image:
                    continue
                img = child[0]
                figure = etree.Element("figure", {"class": "figure"})
                img.tail = None
                figure.append(img)
                caption = img.attrib.pop("title", "").strip()
                if caption:
                    etree.SubElement(figure, "figcaption").text = caption
                parent.remove(child)
                parent.insert(index, figure)


class AxExtension(Extension):
    def __init__(self, **kwargs) -> None:
        self.config = {"base_path": ["/", "사이트 하위 경로 (예: /ax/)"]}
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown) -> None:  # noqa: N802 (Python-Markdown API 이름)
        md.preprocessors.register(FormulaPreprocessor(md), "ax_formula", FORMULA_PRIORITY)
        md.treeprocessors.register(FigureTreeprocessor(md, self.getConfig("base_path")), "ax_figure", FIGURE_PRIORITY)
