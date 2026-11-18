"""빌드 공용 모델: 경로·URL·글 데이터·오류 타입. 모든 링크는 Urls 에서만 만든다."""
from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

ROOT: Path = Path(__file__).resolve().parent.parent
POSTS_DIR: Path = ROOT / "posts"
OUT_DIR: Path = ROOT / "_site"
KST = dt.timezone(dt.timedelta(hours=9))
GIT_TIMEOUT_SEC: int = 10


class BuildError(RuntimeError):
    """원고·설정 오류 또는 산출물 자기검사 실패."""


@dataclass(frozen=True)
class Urls:
    """GitHub Pages 하위 경로(/ax/)를 한 곳에서 관리한다."""
    base_url: str

    @property
    def base_path(self) -> str:
        return urlparse(self.base_url).path.rstrip("/") + "/"

    def path(self, rel: str = "") -> str:
        return self.base_path + rel

    def absolute(self, rel: str = "") -> str:
        return self.base_url.rstrip("/") + "/" + rel


@dataclass
class Post:
    title: str
    slug: str
    summary: str
    date: dt.date
    updated: dt.date
    concepts: list[str]
    faq: list[dict[str, str]]
    body_html: str
    source: str
    category: str
    reading_minutes: int
    toc: list[dict[str, str]]  # 본문 h2 → [{"id", "name"}]
    concept_entries: list[dict] = field(default_factory=list)


def write(rel: str, text: str) -> None:
    target = OUT_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def latest_update(posts: list[Post]) -> dt.date:
    return max((post.updated for post in posts), default=dt.date.today())


def git_last_change(rel_path: str) -> dt.date | None:
    """파일의 마지막 커밋 날짜. git 이 없거나 기록이 없으면 None (mtime 은 체크아웃마다 바뀌어 쓰지 않는다)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", rel_path], cwd=ROOT, capture_output=True,
                             text=True, timeout=GIT_TIMEOUT_SEC, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return dt.date.fromisoformat(out) if out else None
