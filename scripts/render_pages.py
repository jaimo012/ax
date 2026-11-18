"""HTML 페이지 생성: 글·목록·개념 사전·404. 모든 링크는 Urls 로만 만든다."""
from __future__ import annotations

import datetime as dt
from urllib.parse import quote

from jinja2 import Environment

from scripts.site_extras import article_jsonld, faq_jsonld, glossary_jsonld
from scripts.site_model import Post, Urls, write


def korean_date(value: dt.date) -> str:
    return f"{value.year}년 {value.month}월 {value.day}일"


def make_page(title: str, description: str, canonical: str | None, jsonld: list[str], og_type: str = "website") -> dict:
    return {"title": title, "description": description, "canonical": canonical, "og_type": og_type, "jsonld": jsonld}


def render_post(env: Environment, common: dict, post: Post, older: Post | None, newer: Post | None) -> None:
    site, urls = common["site"], common["urls"]
    mailto = f"mailto:{site['contact_email']}?subject={quote('커피챗: ' + post.title)}"
    jsonld = [article_jsonld(post, site, urls)] + ([faq_jsonld(post)] if post.faq else [])
    page = make_page(post.title, post.summary, urls.absolute(f"{post.slug}/"), jsonld, og_type="article")
    html = env.get_template("post.html").render(**common, page=page, post=post, mailto=mailto, older=older, newer=newer)
    write(f"{post.slug}/index.html", html)


def render_pages(env: Environment, site: dict, concepts: list[dict], posts: list[Post], urls: Urls) -> None:
    """posts 는 최신순. 이전·다음 글은 2편 이상일 때만 템플릿이 보여준다."""
    common = {"site": site, "urls": urls, "year": dt.date.today().year, "show_neighbors": len(posts) >= 2}
    for index, post in enumerate(posts):
        newer = posts[index - 1] if index > 0 else None
        older = posts[index + 1] if index + 1 < len(posts) else None
        render_post(env, common, post, older, newer)

    used_by = {c["id"]: [p for p in posts if c["id"] in p.concepts] for c in concepts}
    page = make_page(f"개념 사전 | {site['site_name']}", f"{site['site_name']}에서 쓰는 개념의 정의 모음",
                     urls.absolute("glossary/"), [glossary_jsonld(concepts, site, urls)])
    write("glossary/index.html", env.get_template("glossary.html").render(**common, page=page, concepts=concepts, used_by=used_by))
    page = make_page(site["site_name"], site["description"], urls.absolute(), [])
    write("index.html", env.get_template("index.html").render(**common, page=page, posts=posts))
    page = make_page(f"페이지를 찾을 수 없습니다 | {site['site_name']}", site["description"], None, [])  # 404 는 canonical 없음
    write("404.html", env.get_template("404.html").render(**common, page=page))
