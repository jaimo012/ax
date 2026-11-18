"""빌드 산출물 자기검사. 하나라도 어긋나면 BuildError.

- 'career' 문자열 0건 (이 사이트에서 이력서 사이트로 가는 흔적은 어디에도 두지 않는다)
- JSON-LD 가 유효한 JSON 이고 author·문서에 url/sameAs 가 없음
- 모든 내부 링크(절대·상대)가 /ax/ 하위 경로의 실제 파일·앵커를 가리킴
- 필수 산출물 존재
"""
from __future__ import annotations

import html
import json
import posixpath
import re
from pathlib import Path

from scripts.site_model import OUT_DIR, BuildError, Urls

FORBIDDEN_OUTPUT_WORD: str = "career"
REQUIRED_OUTPUTS: tuple[str, ...] = ("index.html", "glossary/index.html", "404.html", "sitemap.xml", "feed.xml", "llms.txt")
EXTERNAL_PREFIXES: tuple[str, ...] = ("mailto:", "https://", "http://", "data:", "tel:")
JSONLD_BLOCK = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
LINK_ATTR = re.compile(r'(?:href|src)="([^"]+)"')
ID_ATTR = re.compile(r'\bid="([^"]+)"')


def resolve_link(urls: Urls, page_rel: str, link: str) -> tuple[Path, str] | None:
    """내부 링크를 (_site 안 파일, #조각)으로 푼다. 외부 링크·같은 페이지 앵커는 None."""
    absolute_prefix = urls.base_url.rstrip("/") + "/"
    if link.startswith(absolute_prefix):
        link = urls.base_path + link[len(absolute_prefix):]
    elif link.startswith(EXTERNAL_PREFIXES):
        return None
    elif link.startswith("#"):  # 같은 페이지 앵커(목차 등)도 실제 id 가 있는지 본다
        return OUT_DIR / page_rel, link[1:]
    if not link.startswith("/"):  # 상대 링크는 페이지 위치 기준으로 푼다 (#조각은 떼고 경로만 정규화)
        rel_path, hash_mark, rel_fragment = link.partition("#")
        page_dir = posixpath.dirname(urls.base_path + page_rel)
        resolved = posixpath.normpath(posixpath.join(page_dir, rel_path))
        link = resolved + ("/" if rel_path.endswith("/") else "") + hash_mark + rel_fragment
    if not link.startswith(urls.base_path):
        raise BuildError(f"하위 경로({urls.base_path}) 밖을 가리키는 내부 링크: {link}")
    path, _, fragment = link[len(urls.base_path):].partition("#")
    target = OUT_DIR / path
    return (target / "index.html" if path == "" or path.endswith("/") else target), fragment


def check_jsonld(rel: str, text: str) -> list[str]:
    problems: list[str] = []
    for block in JSONLD_BLOCK.findall(text):
        try:
            data = json.loads(block)
        except json.JSONDecodeError as exc:
            problems.append(f"{rel}: JSON-LD 파싱 실패 {exc}")
            continue
        author = data.get("author") or {}
        if "url" in author or "sameAs" in author or "sameAs" in data:
            problems.append(f"{rel}: JSON-LD 에 url/sameAs 가 있다")
    return problems


def check_links(urls: Urls, rel: str, text: str) -> list[str]:
    problems: list[str] = []
    for link in LINK_ATTR.findall(html.unescape(text)):
        try:
            found = resolve_link(urls, rel, link)
        except BuildError as exc:
            problems.append(f"{rel}: {exc}")
            continue
        if found is None:
            continue
        target, fragment = found
        if not target.exists():
            problems.append(f"{rel}: 깨진 내부 링크 {link}")
        elif fragment and fragment not in ID_ATTR.findall(target.read_text(encoding="utf-8")):
            problems.append(f"{rel}: 없는 앵커 {link}")
    return problems


def verify_output(urls: Urls) -> None:
    problems: list[str] = []
    for file in sorted(p for p in OUT_DIR.rglob("*") if p.is_file()):
        text = file.read_text(encoding="utf-8", errors="replace")
        rel = file.relative_to(OUT_DIR).as_posix()
        if FORBIDDEN_OUTPUT_WORD in text.lower():
            problems.append(f"{rel}: '{FORBIDDEN_OUTPUT_WORD}' 문자열이 있다")
        if file.suffix == ".html":
            problems += check_jsonld(rel, text) + check_links(urls, rel, text)
    problems += [f"필수 산출물 없음: {name}" for name in REQUIRED_OUTPUTS if not (OUT_DIR / name).exists()]
    if problems:
        raise BuildError("산출물 자기검사 실패:\n  " + "\n  ".join(problems))
