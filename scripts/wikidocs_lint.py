#!/usr/bin/env python3
"""위키독스 깃허브 연동 원고 린터.

검사 항목 (위키독스 렌더링/PDF 변환에서 실제로 문제가 되는 것만):
  1. 이모지 (PDF 변환 실패, 기기별 깨짐)
  2. 수평선 (---, ***, ___) - 표 구분자 |---| 는 제외
  3. pages/ 본문의 H1, H2 (페이지 제목 중복 / PDF 강제 페이지 나눔)
  4. 목록 앞 빈 줄 누락
  5. 중첩 목록 2칸 들여쓰기 (위키독스는 4칸)
  6. 본문의 이스케이프 안 된 $ (MathJax 오인)
  7. 화살표 특수기호 (-> 로 대체)
  8. TOC.md 에 없는 pages 파일 / TOC.md 가 가리키는 없는 파일
  9. 페이지 본문 첫 제목이 TOC 제목과 중복

사용법:
    python3 scripts/wikidocs_lint.py            # 저장소 전체
    python3 scripts/wikidocs_lint.py pages/07-0-....md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
    "\U0001F1E6-\U0001F1FF\u2190-\u21FF\u2B05\u2B06\u2B07\u2934\u2935"
    "\uFE0F\u2049\u203C]"
)
HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+\.)\s+")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
DASH = re.compile(r"\$")


def in_code(line: str, state: bool) -> bool:
    """fence 상태 갱신용. 반환값은 '이 줄이 코드 안'인지."""
    if line.strip().startswith("```"):
        return True
    return state


def lint_file(path: Path, tocs: dict[str, str]) -> list[str]:
    problems: list[str] = []
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    rel = path.relative_to(ROOT)
    is_page = path.parent.name == "pages"

    fence = False
    prev_line = ""
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        is_fence_line = stripped.startswith("```")
        if is_fence_line:
            prev_line = line
            fence = not fence
            continue
        if fence:
            prev_line = line
            continue

        # 2. 수평선
        if HR.match(line):
            problems.append(f"{rel}:{i}: 수평선 사용 금지 ({stripped})")

        # 3. 제목 계층
        m = HEADING.match(line)
        if m and is_page:
            level = len(m.group(1))
            if level == 1:
                problems.append(f"{rel}:{i}: 본문 H1 금지 (페이지 제목이 자동 출력됨)")
            elif level == 2:
                problems.append(f"{rel}:{i}: H2 자제 (PDF 변환 시 페이지 나눔). ### 부터 사용")

        # 1. 이모지
        for ch in line:
            if EMOJI.match(ch):
                problems.append(f"{rel}:{i}: 이모지/화살표 문자 '{ch}' 사용 금지")
                break

        # 4. 목록 앞 빈 줄
        if LIST_ITEM.match(line) and not LIST_ITEM.match(prev_line) \
                and prev_line.strip() and not prev_line.strip().startswith((">", "|")):
            problems.append(f"{rel}:{i}: 목록 앞 빈 줄 필요")

        # 5. 중첩 목록 들여쓰기
        lm = LIST_ITEM.match(line)
        if lm:
            indent = len(lm.group(1).expandtabs(4))
            if indent % 4 != 0:
                problems.append(f"{rel}:{i}: 중첩 목록은 4칸 단위 (현재 {indent}칸)")

        # 6. 이스케이프 안 된 $
        cleared = re.sub(r"`[^`]*`", "", line)
        if DASH.search(cleared) and "\\$" not in line:
            problems.append(f"{rel}:{i}: 본문 $ 는 \\$ 로 이스케이프 (코드가 아니라면)")

        prev_line = line

    if fence:
        problems.append(f"{rel}: 코드 블록(```)이 닫히지 않음")

    # 9. TOC 제목과 본문 첫 제목 중복
    if is_page and str(rel / "") in tocs:
        title = tocs[str(rel)]
        base = re.sub(r"^[0-9]+(-[0-9]+)?\.\s*", "", title).strip()
        for line in lines:
            hm = HEADING.match(line)
            if hm:
                if hm.group(2).strip() == base:
                    problems.append(f"{rel}: 본문 첫 제목이 TOC 제목과 중복 ({base})")
                break

    return problems


def read_toc() -> tuple[dict[str, str], list[str]]:
    problems: list[str] = []
    toc = ROOT / "TOC.md"
    mapping: dict[str, str] = {}
    if not toc.exists():
        return mapping, ["TOC.md 없음"]
    for i, line in enumerate(toc.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\s*)- \[(.+?)\]\((.+?)\)\s*$", line)
        if not m:
            problems.append(f"TOC.md:{i}: 목차 형식이 아님 (- [제목](pages/파일.md))")
            continue
        indent = len(m.group(1))
        if indent % 2 != 0:
            problems.append(f"TOC.md:{i}: 들여쓰기는 2칸 단위")
        target = m.group(3)
        mapping[target] = m.group(2)
        if not (ROOT / target).exists():
            problems.append(f"TOC.md:{i}: 파일 없음 -> {target}")
    return mapping, problems


def main() -> int:
    args = sys.argv[1:]
    mapping, problems = read_toc()

    if args:
        targets = [Path(a) for a in args]
    else:
        targets = sorted((ROOT / "pages").glob("*.md")) + [ROOT / "README.md", ROOT / "TOC.md"]
        targets = [p for p in targets if p.exists()]

    for p in targets:
        if not p.is_absolute():
            p = ROOT / p
        if p.suffix != ".md":
            continue
        rel_to_root = p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
        problems.extend(lint_file(p, mapping))

    if not args:
        listed = {k for k in mapping}
        for f in sorted((ROOT / "pages").glob("*.md")):
            key = f"pages/{f.name}"
            if key not in listed:
                problems.append(f"{key}: TOC.md 에 없음 (책에 나오지 않음)")

    if problems:
        for p in problems:
            print(p)
        print(f"\n{len(problems)}건 문제")
        return 1

    print("린트 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
