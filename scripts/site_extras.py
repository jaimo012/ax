"""JSON-LD 와 부가 산출물(sitemap.xml · feed.xml · llms.txt).

JSON-LD 는 문자열을 손으로 잇지 않는다 → dict → json.dumps. author 에는 이름만 둔다(url·sameAs 금지).
"""
from __future__ import annotations

import datetime as dt
import html
import json
from email.utils import format_datetime

from scripts.site_model import KST, Post, Urls, git_last_change, latest_update, write


def to_jsonld(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")


def article_jsonld(post: Post, site: dict, urls: Urls) -> str:
    return to_jsonld({
        "@context": "https://schema.org", "@type": "Article",
        "headline": post.title, "description": post.summary,
        "datePublished": post.date.isoformat(), "dateModified": post.updated.isoformat(),
        "author": {"@type": "Person", "name": site["author_name"]},
        "inLanguage": site["lang"], "mainEntityOfPage": urls.absolute(f"{post.slug}/"),
    })


def faq_jsonld(post: Post) -> str:
    return to_jsonld({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": item["q"], "acceptedAnswer": {"@type": "Answer", "text": item["a"]}}
            for item in post.faq
        ],
    })


def glossary_jsonld(concepts: list[dict], site: dict, urls: Urls) -> str:
    set_url = urls.absolute("glossary/")
    return to_jsonld({
        "@context": "https://schema.org", "@type": "DefinedTermSet", "@id": set_url, "url": set_url,
        "name": f"{site['site_name']} 개념 사전", "inLanguage": site["lang"],
        "hasDefinedTerm": [
            {"@type": "DefinedTerm", "@id": f"{set_url}#{c['id']}", "url": f"{set_url}#{c['id']}", "termCode": c["id"],
             "name": c["ko"], "alternateName": c["en"], "description": c["definition"], "inDefinedTermSet": set_url}
            for c in concepts
        ],
    })


def render_sitemap(posts: list[Post], urls: Urls) -> None:
    last_post = latest_update(posts)
    concepts_changed = git_last_change("concepts.yml")
    glossary_last = max(last_post, concepts_changed) if concepts_changed else last_post
    entries = [(urls.absolute(), max(last_post, glossary_last)), (urls.absolute("glossary/"), glossary_last)]
    entries += [(urls.absolute(f"{p.slug}/"), p.updated) for p in posts]
    rows = "".join(f"  <url><loc>{html.escape(loc)}</loc><lastmod>{mod.isoformat()}</lastmod></url>\n"
                   for loc, mod in entries)
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n")


def rfc822(value: dt.date) -> str:
    return format_datetime(dt.datetime(value.year, value.month, value.day, 9, 0, tzinfo=KST))


def render_feed(site: dict, posts: list[Post], urls: Urls) -> None:
    esc = html.escape
    items = "".join(
        f"    <item>\n      <title>{esc(p.title)}</title>\n      <link>{esc(urls.absolute(p.slug + '/'))}</link>\n"
        f"      <guid isPermaLink=\"true\">{esc(urls.absolute(p.slug + '/'))}</guid>\n"
        f"      <pubDate>{rfc822(p.date)}</pubDate>\n      <description>{esc(p.summary)}</description>\n    </item>\n"
        for p in posts
    )
    write("feed.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n  <channel>\n'
          f"    <title>{esc(site['site_name'])}</title>\n    <link>{esc(urls.absolute())}</link>\n"
          f"    <description>{esc(site['description'])}</description>\n    <language>{esc(site['lang'])}</language>\n"
          f"    <lastBuildDate>{rfc822(latest_update(posts))}</lastBuildDate>\n"
          f"    <atom:link href=\"{esc(urls.absolute('feed.xml'))}\" rel=\"self\" type=\"application/rss+xml\"/>\n"
          + items + "  </channel>\n</rss>\n")


def render_llms(site: dict, concepts: list[dict], posts: list[Post], urls: Urls) -> None:
    lines = [f"# {site['site_name']}", "", f"> {site['description']}", "", f"저자: {site['author_name']}", "",
             "## 개념 사전", "", f"- [개념 사전]({urls.absolute('glossary/')}): 이 사이트의 글에서 쓰는 개념 정의 모음"]
    lines += [f"  - [{c['ko']} ({c['en']})]({urls.absolute('glossary/')}#{c['id']}): {c['definition']}" for c in concepts]
    lines += ["", "## 글", ""]
    lines += [f"- [{p.title}]({urls.absolute(p.slug + '/')}): {p.summary}" for p in posts] or ["- (아직 발행한 글이 없습니다)"]
    write("llms.txt", "\n".join(lines) + "\n")
