#!/usr/bin/env python3
"""위키독스 책에 새 장을 추가하고 커밋, 푸시한다.

발행 회차가 끝날 때마다, 또는 쓸 만한 사례가 하나 쌓일 때마다 실행한다.

    python3 scripts/add_chapter.py --title "09. 새 장 제목" --file drafts/new.md
    python3 scripts/add_chapter.py --title "09-1. 하위 장" --file drafts/new.md --parent "09"
    python3 scripts/add_chapter.py ... --no-push      # 커밋까지만

동작:
  1. --file 원고를 읽어 pages/ 에 저장 (파일명은 제목에서 만든다)
  2. TOC.md 에 항목 추가 (--parent 가 있으면 그 항목 아래 2칸 들여쓰기)
  3. 린트 실행, 문제가 있으면 중단
  4. git add, commit, push
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages"
TOC = ROOT / "TOC.md"


def slugify(title: str) -> str:
    body = re.sub(r"^[0-9]+(-[0-9]+)?\.\s*", "", title).strip()
    body = re.sub(r"[^0-9A-Za-z가-힣]+", "-", body).strip("-")
    return body or "chapter"


def page_filename(title: str) -> str:
    num = re.match(r"^([0-9]+(?:-[0-9]+)?)\.", title)
    prefix = num.group(1) if num else "99"
    return f"{prefix}-{slugify(title)}.md"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True, help='예: "09. 새 장 제목"')
    ap.add_argument("--file", required=True, help="원고 마크다운 경로")
    ap.add_argument("--parent", default=None, help='부모 장 번호 예: "09" (하위 장으로 넣을 때)')
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    src = Path(args.file)
    if not src.is_absolute():
        src = (Path.cwd() / src).resolve()
    if not src.exists():
        print(f"원고 파일 없음: {src}")
        return 1

    name = page_filename(args.title)
    dest = PAGES / name
    if dest.exists():
        print(f"이미 있음: pages/{name} (제목 번호를 확인하세요)")
        return 1

    PAGES.mkdir(exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    original_toc = TOC.read_text(encoding="utf-8")
    toc_lines = original_toc.splitlines()
    entry = f"- [{args.title}](pages/{name})"
    indent = ""

    if args.parent:
        idx = None
        for i, line in enumerate(toc_lines):
            if re.match(rf"^- \[{re.escape(args.parent)}\.", line):
                idx = i
                break
        if idx is None:
            print(f"부모 항목을 찾지 못함: {args.parent}")
            return 1
        indent = "  "
        insert_at = idx + 1
        while insert_at < len(toc_lines) and toc_lines[insert_at].startswith("  - "):
            insert_at += 1
        toc_lines.insert(insert_at, indent + entry)
    else:
        insert_at = len(toc_lines)
        while insert_at > 0 and not toc_lines[insert_at - 1].strip():
            insert_at -= 1
        if insert_at > 0:
            toc_lines.insert(insert_at, entry)
        else:
            toc_lines.append(entry)

    text = "\n".join(toc_lines).rstrip() + "\n"
    TOC.write_text(text, encoding="utf-8")

    lint = run([sys.executable, "scripts/wikidocs_lint.py"], check=False)
    print(lint.stdout.strip() or lint.stderr.strip())
    if lint.returncode != 0:
        dest.unlink(missing_ok=True)
        TOC.write_text(original_toc, encoding="utf-8")
        print("린트 실패. 원고를 고친 뒤 다시 실행하세요 (이번 변경은 되돌렸습니다).")
        return 1

    run(["git", "add", "pages", "TOC.md", "README.md", "assets"])
    msg = f"chapter: {args.title}"
    commit = run(["git", "commit", "-m", msg], check=False)
    if commit.returncode != 0:
        print(commit.stdout.strip() + commit.stderr.strip())
        print("커밋할 변경이 없거나 커밋에 실패했습니다.")
        return commit.returncode

    if args.no_push:
        print("커밋 완료 (푸시 생략)")
        return 0

    push = run(["git", "push"], check=False)
    print((push.stdout or "") + (push.stderr or ""))
    if push.returncode != 0:
        print("푸시 실패. 자격 증명을 확인하세요.")
        return push.returncode

    print(f"완료: pages/{name}")
    print("위키독스에서 몇 분 뒤 반영됩니다. 안 되면 책 수정 > 깃허브 탭의 '지금 동기화'를 누르세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
