"""발행 대상 파일에서 금지어를 찾는다. 하나라도 걸리면 exit 1.

금지어 목록은 레포에 두지 않는다(public 레포라 목록 자체가 노출되면 안 된다).
- CI   : 환경변수 BANNED_TERMS (GitHub Secret, 줄바꿈 구분) → 작업 폴더 파일 검사
- 로컬 : --terms-file ~/.ax_banned_terms --staged (hooks/pre-commit) → 실제로 커밋될 스테이징 내용 검사

목록이 비어 있으면 '통과'가 아니라 실패로 처리한다 — 목록 없는 검사는 영원히 울리지 않는 센서다.
CI 로그는 public 이라 걸린 단어를 그대로 찍지 않고 '금지어 #번호'로 가린다.

사용: python scripts/check_banned.py [--terms-file PATH] [--staged] [검사할 경로 ...]
표준 라이브러리만 쓴다(훅에서 가상환경 없이 돈다).
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parent.parent
# 원고·설정뿐 아니라 공개 화면에 찍히는 템플릿·스타일, 레포 첫 화면인 README 까지 본다
DEFAULT_TARGETS: tuple[str, ...] = ("posts", "concepts.yml", "site.yml", "templates", "static", "README.md")
TEXT_SUFFIXES: tuple[str, ...] = (".md", ".yml", ".yaml", ".txt", ".html", ".css")
EXIT_FOUND: int = 1
GIT_TIMEOUT_SEC: int = 20

logger = logging.getLogger("check_banned")


def load_terms(terms_file: str | None) -> list[str]:
    """줄바꿈 구분 목록을 읽는다. 빈 줄과 # 으로 시작하는 줄은 건너뛴다."""
    if terms_file:
        path = Path(terms_file).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"금지어 목록 파일이 없다: {path}")
        raw = path.read_text(encoding="utf-8-sig")
    else:
        raw = os.environ.get("BANNED_TERMS", "")
    terms = [line.strip() for line in raw.splitlines()]
    return [term for term in terms if term and not term.startswith("#")]


def is_target(rel: str, targets: list[str]) -> bool:
    rel = rel.replace("\\", "/")
    if not rel.lower().endswith(TEXT_SUFFIXES):
        return False
    return any(rel == t.rstrip("/") or rel.startswith(t.rstrip("/") + "/") for t in targets)


def worktree_sources(targets: list[str]) -> list[tuple[str, str]]:
    """(표시 이름, 내용) 목록 — 작업 폴더 기준."""
    sources: list[tuple[str, str]] = []
    for target in targets:
        path = Path(target) if Path(target).is_absolute() else ROOT / target
        files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else ([path] if path.is_file() else [])
        for file in files:
            if file.suffix.lower() in TEXT_SUFFIXES:
                try:
                    name = file.relative_to(ROOT).as_posix()
                except ValueError:
                    name = file.as_posix()
                sources.append((name, file.read_text(encoding="utf-8-sig", errors="replace")))
    return sources


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, timeout=GIT_TIMEOUT_SEC, check=True
                          ).stdout.decode("utf-8", errors="replace")


def staged_sources(targets: list[str]) -> list[tuple[str, str]]:
    """(표시 이름, 내용) 목록 — 스테이징 영역 기준(실제로 커밋될 내용)."""
    names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0")
    return [(name, git("show", f":{name}")) for name in names if name and is_target(name, targets)]


def scan(sources: list[tuple[str, str]], terms: list[str], mask: bool) -> list[str]:
    folded = [(index, term, term.casefold()) for index, term in enumerate(terms, start=1)]
    hits: list[str] = []
    for name, text in sources:
        for line_no, line in enumerate(text.splitlines(), start=1):
            line_folded = line.casefold()
            hits += [f"{name}:{line_no}: {f'금지어 #{index}' if mask else term}"
                     for index, term, term_folded in folded if term_folded in line_folded]
    return hits


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="[금지어 검사] %(message)s")
    parser = argparse.ArgumentParser(description="발행 대상 파일 금지어 검사")
    parser.add_argument("--terms-file", help="줄바꿈 구분 금지어 목록 파일 (없으면 환경변수 BANNED_TERMS)")
    parser.add_argument("--staged", action="store_true", help="작업 폴더 대신 스테이징된 내용을 검사 (커밋 훅용)")
    parser.add_argument("paths", nargs="*", help="검사할 파일·폴더 (기본: 원고·설정·템플릿·스타일·README)")
    args = parser.parse_args()

    try:
        terms = load_terms(args.terms_file)
    except FileNotFoundError as exc:
        logger.error("실패: %s", exc)
        return EXIT_FOUND
    if not terms:
        logger.error("실패: 금지어 목록이 비어 있다(%s). 목록을 등록한 뒤 다시 실행한다.",
                     args.terms_file or "환경변수 BANNED_TERMS")
        return EXIT_FOUND

    targets = args.paths or list(DEFAULT_TARGETS)
    try:
        sources = staged_sources(targets) if args.staged else worktree_sources(targets)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("실패: 검사 대상을 읽지 못했다: %s", exc)
        return EXIT_FOUND
    hits = scan(sources, terms, mask=os.environ.get("CI") == "true")
    if hits:
        logger.error("%d건 발견. 커밋·배포를 중단한다:\n  %s", len(hits), "\n  ".join(hits))
        return EXIT_FOUND
    logger.info("통과: 파일 %d개 · 금지어 %d개%s", len(sources), len(terms), " (스테이징 기준)" if args.staged else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
