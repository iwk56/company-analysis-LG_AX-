"""재무상태표 주요 계정의 증감과 연결되는 사업보고서 주석을 추린다."""
import re

from .dart_docs import financial_notes, note_text

NOTE_TERMS = (
    (("매출채권", "기타채권"), ("매출채권", "채권")),
    (("재고", "상품"), ("재고자산",)),
    (("유형자산", "건설중", "설비"), ("유형자산",)),
    (("무형자산",), ("무형자산",)),
    (("금융상품", "금융자산"), ("금융상품", "금융자산")),
    (("차입",), ("차입금",)),
    (("사채",), ("사채",)),
    (("리스",), ("리스",)),
    (("매입채무", "미지급금"), ("매입채무", "매입채무및기타채무")),
    (("계약부채", "선수금"), ("계약부채",)),
)


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _changed_accounts(report: dict, top: int) -> list[tuple[str, dict, dict]]:
    details = report.get("results", {}).get("balance_details") or {}
    year = report.get("base_year")
    if not isinstance(year, int):
        return []
    current = details.get(str(year), details.get(year, {}))
    previous = details.get(str(year - 1), details.get(year - 1, {}))
    if not current or not previous:
        return []

    changed = []
    for group in ("assets", "liabilities", "equity"):
        before = {item["key"]: item for item in (previous.get("accounts") or {}).get(group, [])}
        rows = []
        for item in (current.get("accounts") or {}).get(group, []):
            old = before.get(item["key"])
            if old is None or old.get("value") is None or item.get("value") is None:
                continue
            delta = item["value"] - old["value"]
            if delta:
                rows.append((abs(delta), item, old))
        rows.sort(key=lambda row: row[0], reverse=True)
        changed.extend((group, item, old) for _, item, old in rows[:top])
    return changed


def _account_note(notes: str, name: str) -> tuple[str | None, str | None]:
    normalized = _norm(name)
    terms = next((keywords for account_terms, keywords in NOTE_TERMS
                  if any(term in normalized for term in account_terms)), (name,))
    excerpt = next((text for keyword in terms if (text := note_text(notes, keyword))), None)
    if not excerpt:
        return None, None
    title = excerpt.splitlines()[0]
    lines, length = [], 0
    for line in excerpt.splitlines():
        if length + len(line) + 1 > 2400:
            break
        lines.append(line)
        length += len(line) + 1
    return title, "\n".join(lines)


def collect_balance_note_items(xml: str | None, report: dict, top: int = 4) -> dict:
    """주요 세부 계정에 대응하는 기준연도 주석을 계정 키별로 묶는다."""
    notes = financial_notes(xml or "") if xml else None
    changed = _changed_accounts(report, top)
    items = []
    for group, account, previous in changed:
        title, excerpt = _account_note(notes, account["name"]) if notes else (None, None)
        items.append({
            "key": account["key"],
            "name": account["name"],
            "group": group,
            "prior": previous["value"],
            "current": account["value"],
            "change": account["value"] - previous["value"],
            "note_title": title,
            "note_excerpt": excerpt,
        })
    return {"year": report.get("base_year"), "items": items}


def balance_note_text(xml: str | None, report: dict, top: int = 2) -> str | None:
    """기준연도 주요 자산·부채 변동의 DART 주석 발췌를 반환한다."""
    notes = financial_notes(xml or "") if xml else None
    changed = _changed_accounts(report, top)
    if not notes or not changed:
        return None

    excerpts: list[str] = []
    seen: set[str] = set()
    for group, account, previous in changed:
        if group == "equity":
            continue
        title, excerpt = _account_note(notes, account["name"])
        if excerpt and title not in seen:
            seen.add(title)
            excerpts.append(excerpt)

    if not excerpts:
        return None
    return (
        f"{report['base_year']}년 사업보고서 재무제표 주석 중 주요 자산·부채·자본 계정 변동 관련 발췌입니다. "
        "공시에 기재된 내역만 원인 설명에 사용합니다.\n" + "\n\n".join(excerpts[:4])
    )
