"""posts/*.md + concepts.yml + site.yml → _site/ 정적 사이트.

본문·목록·개념 정의는 모두 빌드 시점에 HTML 로 완성한다(JS 로 불러오지 않는다 — AI 크롤러 대부분이 JS 를 실행하지 않음).
빌드 마지막에 산출물을 자기검사하고(scripts/verify_site.py), 하나라도 어긋나면 exit 1 로 멈춘다.

실행: python build.py
"""
from __future__ import annotations

import datetime as dt
import html
import logging
import re
import shutil
import sys

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markdown.extensions.toc import slugify_unicode

from scripts.md_ext import AxExtension, MarkdownContentError
from scripts.render_pages import korean_date, render_pages
from scripts.site_extras import render_feed, render_llms, render_sitemap
from scripts.site_model import OUT_DIR, POSTS_DIR, ROOT, BuildError, Post, Urls
from scripts.verify_site import verify_output

for _stream in (sys.stdout, sys.stderr):  # 윈도우 콘솔(cp949)에서 한글 로그가 깨지지 않게
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("build")

POST_FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n(.*))?\Z", re.DOTALL)
TAG = re.compile(r"<[^>]+>")
REQUIRED_POST_KEYS: tuple[str, ...] = ("title", "slug", "summary", "date")
REQUIRED_SITE_KEYS: tuple[str, ...] = ("site_name", "description", "base_url", "author_name", "contact_email", "lang",
                                       "default_category")
REQUIRED_CONCEPT_KEYS: tuple[str, ...] = ("id", "ko", "en", "definition")
RESERVED_SLUGS: frozenset[str] = frozenset({"glossary", "static", "figures"})
MARKDOWN_EXTENSIONS: tuple[str, ...] = ("extra", "sane_lists", "toc")
CHARS_PER_MINUTE: int = 500  # 한국어 성인 묵독 속도(분당 글자 수) 기준 읽는 시간
FIGURES_DIR_NAME: str = "figures"


# ────────────────────────────────────────────────────────────
# 읽기·검증
# ────────────────────────────────────────────────────────────
def load_yaml(name: str):
    try:
        return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BuildError(f"{name} 읽기 실패: {exc}") from exc


def load_site() -> dict:
    site = load_yaml("site.yml") or {}
    missing = [key for key in REQUIRED_SITE_KEYS if not site.get(key)]
    if missing:
        raise BuildError(f"site.yml 필수 항목 누락: {missing}")
    for key in ("author_name", "contact_email"):
        if "{{" in str(site[key]):
            logger.warning("site.yml 의 %s 가 아직 자리표시자다: %s (공개 화면에 그대로 보인다)", key, site[key])
    return site


def load_concepts() -> list[dict]:
    concepts = load_yaml("concepts.yml") or []
    if not isinstance(concepts, list):
        raise BuildError("concepts.yml 은 목록이어야 한다")
    seen: set[str] = set()
    for index, concept in enumerate(concepts, start=1):
        missing = [key for key in REQUIRED_CONCEPT_KEYS if not concept.get(key)]
        if missing:
            raise BuildError(f"concepts.yml {index}번째 항목 필수 항목 누락: {missing}")
        if concept["id"] in seen:
            raise BuildError(f"concepts.yml id 중복: {concept['id']}")
        seen.add(concept["id"])
        concept.setdefault("description", "")
    return concepts


def as_date(value, source: str, key: str) -> dt.date:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise BuildError(f"{source}: {key} 가 YYYY-MM-DD 형식이 아니다: {value!r}") from exc


def read_front_matter(path) -> tuple[dict, str]:
    found = FRONT_MATTER.match(path.read_text(encoding="utf-8-sig").replace("\r\n", "\n"))
    if not found:
        raise BuildError(f"{path.name}: --- 로 감싼 front matter 가 없다")
    try:
        meta = yaml.safe_load(found.group(1)) or {}
    except yaml.YAMLError as exc:
        raise BuildError(f"{path.name}: front matter YAML 오류: {exc}") from exc
    return meta, found.group(2) or ""


def validate_meta(path, meta: dict, concept_ids: set[str]) -> tuple[dt.date, dt.date]:
    name_match = POST_FILENAME.match(path.name)
    if not name_match:
        raise BuildError(f"{path.name}: 파일명은 YYYY-MM-DD-slug.md (slug 는 영소문자·숫자·하이픈) 형식이어야 한다")
    missing = [key for key in REQUIRED_POST_KEYS if not meta.get(key)]
    if missing:
        raise BuildError(f"{path.name}: front matter 필수 항목 누락: {missing}")
    date = as_date(meta["date"], path.name, "date")
    updated = as_date(meta.get("updated") or date, path.name, "updated")
    if meta["slug"] != name_match.group(2):
        raise BuildError(f"{path.name}: front matter slug({meta['slug']})가 파일명 slug({name_match.group(2)})와 다르다")
    if date.isoformat() != name_match.group(1):
        raise BuildError(f"{path.name}: front matter date({date})가 파일명 날짜와 다르다")
    if updated < date:
        raise BuildError(f"{path.name}: updated 가 date 보다 이르다")
    unknown = [cid for cid in (meta.get("concepts") or []) if cid not in concept_ids]
    if unknown:
        raise BuildError(f"{path.name}: concepts.yml 에 없는 개념 id: {unknown}")
    if any(not isinstance(i, dict) or not i.get("q") or not i.get("a") for i in (meta.get("faq") or [])):
        raise BuildError(f"{path.name}: faq 항목은 q 와 a 가 모두 있어야 한다")
    return date, updated


def parse_post(path, concept_ids: set[str], site: dict, urls: Urls) -> Post:
    meta, body = read_front_matter(path)
    date, updated = validate_meta(path, meta, concept_ids)
    if re.search(r"^# ", body, re.MULTILINE):
        logger.warning("%s: 본문에 # (h1) 제목이 있다. 제목은 front matter title 하나뿐이니 ## 부터 쓴다", path.name)
    converter = markdown.Markdown(extensions=[*MARKDOWN_EXTENSIONS, AxExtension(base_path=urls.base_path)],
                                  extension_configs={"toc": {"slugify": slugify_unicode}})
    try:
        body_html = converter.convert(body)
    except MarkdownContentError as exc:
        raise BuildError(f"{path.name}: {exc}") from exc
    plain_chars = len(re.sub(r"\s+", "", html.unescape(TAG.sub("", body_html))))
    toc = [{"id": t["id"], "name": html.unescape(t["name"])} for t in converter.toc_tokens if t["level"] == 2]
    return Post(title=str(meta["title"]), slug=meta["slug"], summary=str(meta["summary"]).strip(), date=date,
                updated=updated, concepts=list(meta.get("concepts") or []),
                faq=[{"q": str(i["q"]), "a": str(i["a"])} for i in (meta.get("faq") or [])],
                body_html=body_html, source=path.name, category=str(meta.get("category") or site["default_category"]),
                reading_minutes=max(1, round(plain_chars / CHARS_PER_MINUTE)), toc=toc)


def load_posts(concepts: list[dict], site: dict, urls: Urls) -> list[Post]:
    concept_ids = {c["id"] for c in concepts}
    posts = [parse_post(path, concept_ids, site, urls) for path in sorted(POSTS_DIR.glob("*.md"))]
    slugs = [post.slug for post in posts]
    duplicated = sorted({slug for slug in slugs if slugs.count(slug) > 1})
    if duplicated:
        raise BuildError(f"slug 중복: {duplicated}")
    if RESERVED_SLUGS & set(slugs):
        raise BuildError(f"예약된 경로와 같은 slug: {sorted(RESERVED_SLUGS & set(slugs))}")
    by_id = {c["id"]: c for c in concepts}
    for post in posts:
        post.concept_entries = [by_id[cid] for cid in post.concepts]
    return sorted(posts, key=lambda post: (post.date, post.slug), reverse=True)


def main() -> None:
    try:
        site = load_site()
        urls = Urls(site["base_url"])
        concepts = load_concepts()
        posts = load_posts(concepts, site, urls)
        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
        shutil.copytree(ROOT / "static", OUT_DIR / "static")
        if (POSTS_DIR / FIGURES_DIR_NAME).is_dir():
            shutil.copytree(POSTS_DIR / FIGURES_DIR_NAME, OUT_DIR / FIGURES_DIR_NAME)
        env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]),
                          undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
        env.filters["kdate"] = korean_date
        render_pages(env, site, concepts, posts, urls)
        render_sitemap(posts, urls)
        render_feed(site, posts, urls)
        render_llms(site, concepts, posts, urls)
        verify_output(urls)
    except BuildError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    logger.info("산출물 자기검사 통과 (career 0건 · JSON-LD 유효 · 내부 링크·앵커 정상 · 필수 파일 존재)")
    logger.info("빌드 완료: 글 %d편 · 개념 %d개 → %s", len(posts), len(concepts), OUT_DIR.name)


if __name__ == "__main__":
    main()
