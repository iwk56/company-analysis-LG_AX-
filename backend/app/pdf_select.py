"""AI에 넘길 PDF 섹션 글 고르기 (8-D A안, docs/spec.md F3 "PDF에서 읽는 섹션").

앞 12,000자만 자르면 뒤쪽의 중요한 내용(예: LG전자 II-7의 제품별 시장점유율 표, IV의 유동성)이 빠진다. 그래서
1. 섹션을 소제목 단위로 나눈다 (IV 경영진단은 DART 서식의 "1.~6.", II장 섹션은 "가.~")
2. 호출마다 정한 우선순위(소제목 이름의 키워드)대로 블록을 통째로 넣는다. 형식 문장(예측정보 주의사항 등)은 뺀다
3. 상한(섹션당 12,000자, 호출당 30,000자)을 넘는 블록은 숫자 표 줄을 빼 보고(점유율·고객 블록은 표를 남긴다),
   그래도 넘으면 키워드가 많은 문단만 원래 순서대로 넣는다
4. 넣은·뺀 소제목을 기록해 화면에 "일부만 사용"으로 보여준다. 인용 확인은 넘긴 부분이 아니라 섹션 전체로 한다
"""
import re
from dataclasses import dataclass, field

from .pdf_reader import norm

SECTION_LIMIT = 12_000
CALL_LIMIT = 30_000
MIN_LEFT = 200  # 남은 자리가 이보다 작으면 더 채우지 않는다
RESERVE = 3_000  # 큰 블록을 줄일 때 뒤의 우선순위 블록마다 남겨 두는 자리
SUB_MDA = re.compile(r"^\d{1,2}\.\s*\S")
SUB_BUSINESS = re.compile(r"^[가-하]\.\s*\S")


@dataclass
class Rule:
    """섹션 하나를 고르는 규칙. priority는 소제목 키워드 묶음(앞일수록 먼저), exclude는 빼는 소제목, keywords는 문단 점수."""
    limit: int = SECTION_LIMIT
    priority: tuple[tuple[str, ...], ...] = ()
    exclude: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    keep_tables: tuple[str, ...] = ()  # 이 키워드가 소제목·문단에 있으면 표 줄을 빼지 않는다 (예: 점유율)


@dataclass
class Block:
    index: int
    title: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(([self.title] if self.title else []) + self.lines).strip()


@dataclass
class Picked:
    key: str
    label: str
    text: str
    chars_total: int
    used: list[str]  # 넣은 소제목 ("(일부)" 표시 포함)
    skipped: list[str]  # 자리가 모자라 뺀 소제목
    excluded: list[str] = field(default_factory=list)  # 형식 문장이라 일부러 뺀 소제목 (예: 예측정보에 대한 주의사항)

    @property
    def partial(self) -> bool:
        """상한 때문에 일부만 넘겼는지 (일부러 뺀 형식 문장은 세지 않는다)."""
        return bool(self.skipped) or any(u.endswith("(일부)") for u in self.used)

    def meta(self) -> dict:
        return {"key": self.key, "label": self.label, "chars_total": self.chars_total, "chars_used": len(self.text),
                "partial": self.partial, "used": self.used, "skipped": self.skipped, "excluded": self.excluded}


def section_text(section: dict) -> str:
    return "\n".join(c["text"] for c in section.get("pages") or [])


LETTERS = "가나다라마바사아자차카타파하"


def _order(title: str, mda: bool) -> int | None:
    """소제목 번호의 순서(0부터). 'IV'의 '1.' → 0, II장의 '가.' → 0."""
    head = title.split(".", 1)[0].strip()
    if mda:
        return int(head) - 1 if head.isdigit() else None
    return LETTERS.index(head) if len(head) == 1 and head in LETTERS else None


def split_blocks(section: dict) -> list[Block]:
    """첫 줄(섹션 제목)을 빼고 소제목 줄에서 나눈다. 소제목 앞의 글은 제목 없는 블록.
    소제목은 가→나→다(경영진단은 1→2→3) 순서대로 나올 때만 인정한다. PDF 줄바꿈 때문에
    '…있습니' 다음 줄이 '다. 한편, …'으로 시작하는 경우를 소제목으로 잘못 보지 않기 위해서다."""
    lines = section_text(section).split("\n")[1:]
    mda = section["key"] == "mda"
    pat = SUB_MDA if mda else SUB_BUSINESS
    blocks = [Block(0, "")]
    expected, prev = 0, ""
    for raw in lines:
        s = raw.strip()
        wrapped = s.startswith("다.") and prev.endswith("니")  # '…있습니' + '다. 한편, …' (줄바꿈으로 갈라진 '니다.')
        if s:
            prev = s
        if pat.match(s) and len(norm(s)) <= 40 and _order(s, mda) == expected and not wrapped:
            blocks.append(Block(len(blocks), s))
            expected += 1
        else:
            blocks[-1].lines.append(raw)
    return [b for b in blocks if b.text]


def is_table_line(line: str) -> bool:
    """숫자 위주의 표 줄 (재무 숫자는 DART API 값을 쓰므로 AI에 넘길 필요가 적다)."""
    t = re.sub(r"\s", "", line)
    if not t:
        return True
    digits = len(re.findall(r"[\d,.%()\-△▲]", t))
    return digits / len(t) >= 0.4 or (len(t) < 25 and digits / len(t) >= 0.2 and not re.search(r"(다|요|음|함|됨)\.?$", t))


NEAR = 3  # 점유율 같은 키워드 줄 뒤 몇 줄까지 표 줄을 남길지 (LG전자: "TV 세계시장점유율" 다음 줄이 "15.3% 16.1% 16.3%")


MAX_TABLE_RUN = 20  # 키워드 줄 뒤 표가 이어지면 이 줄 수까지 남긴다 (DART 원문은 표 한 행이 여러 줄로 나뉜다: "DRAM | 34.3%" / "39.1% | 36.3% …")


def _kept_table_lines(lines: list[str], rule: Rule) -> list[bool]:
    """줄마다 '키워드 뒤 표'로 남길지. 키워드 줄 뒤 NEAR줄, 그리고 그 뒤로 표 줄이 끊기지 않고 이어지는 동안(최대 MAX_TABLE_RUN줄)."""
    out, last_kw, running = [], -NEAR - 1, False
    for i, x in enumerate(lines):
        if any(k in norm(x) for k in rule.keep_tables):
            last_kw, running = i, True
        near = i - last_kw <= NEAR
        # 이어지는 표 줄은 %가 든 줄(점유율 행)만 — 뒤에 붙은 다른 숫자 표(금액)까지 끌고 오지 않는다
        if running and not near and (not is_table_line(x) or "%" not in x or i - last_kw > MAX_TABLE_RUN):
            running = False
        out.append(near or running)
    return out


def _slim(block: Block, rule: Rule) -> str:
    """숫자 표 줄을 뺀 글. 단 keep_tables 키워드가 있는 줄 뒤의 표(점유율 표 등)는 남긴다."""
    keep = _kept_table_lines(block.lines, rule)
    lines = [x for x, k in zip(block.lines, keep) if k or not is_table_line(x)]
    return "\n".join(([block.title] if block.title else []) + lines).strip()


def _paragraphs(lines: list[str], rule: Rule) -> list[str]:
    """문장 끝(…다.)이나 짧은 줄에서 문단을 나눈다 (PDF 줄바꿈은 문장 중간에서도 생긴다).
    keep_tables 키워드 줄 뒤 NEAR줄은 끊지 않아 '점유율 제목 + 숫자 행'이 한 문단에 남는다."""
    out, cur = [], []
    keep = _kept_table_lines(lines, rule)
    for i, line in enumerate(lines):
        cur.append(line)
        s = line.strip()
        in_table = i + 1 < len(lines) and keep[i + 1] and is_table_line(lines[i + 1])  # 다음 줄이 남길 표면 끊지 않는다
        if not in_table and (s.endswith(("다.", "다", "음.", "함.")) or len(s) < 25):
            out.append("\n".join(cur))
            cur = []
    if cur:
        out.append("\n".join(cur))
    return [p for p in out if p.strip()]


def _score(text: str, keywords: tuple[str, ...]) -> int:
    return sum(text.count(k) for k in keywords)


def _rank(block: Block, rule: Rule) -> tuple[float, int, int]:
    """소제목 이름이 우선순위 키워드와 맞으면 그 순위, 이름은 안 맞아도 내용에 키워드가 있으면 그 순위 바로 뒤.
    (SK하이닉스 시장점유율 표는 '나. 회사의 현황' 안에 있다)"""
    t = norm(block.title)
    n = len(rule.priority)
    by_title = next((i for i, kws in enumerate(rule.priority) if any(k in t for k in kws)), n)
    by_body = next((i + 0.5 for i, kws in enumerate(rule.priority) if any(k in block.text for k in kws)), n)
    rank = min(by_title, by_body)
    # 우선순위에 맞는 블록끼리는 문서 순서대로 (작은 조직 설명이 큰 실적 표에 밀려 빠지지 않게), 나머지는 키워드 점수 순
    return rank, (block.index if rank < n else -_score(block.text, rule.keywords)), block.index


def _shrink(block: Block, room: int, rule: Rule) -> tuple[str, bool] | None:
    """블록이 자리보다 클 때: 표 줄 빼기 → 그래도 크면 점수 높은 문단만. (글, 통째인지) 또는 None."""
    keep = any(k in norm(block.title) for k in rule.keep_tables)
    if not keep:
        slim = _slim(block, rule)
        if len(slim) <= room:
            return slim, False
    source = block.text if keep else _slim(block, rule)
    paras = _paragraphs(source.split("\n"), rule)
    order = sorted(range(len(paras)), key=lambda i: (-_score(paras[i], rule.keywords + rule.keep_tables), i))
    chosen, left = [], room
    for i in order:
        p = paras[i]
        if not keep and not any(k in p for k in rule.keep_tables) and all(is_table_line(x) for x in p.split("\n")):
            continue  # 표만 있는 문단은 점유율·고객 블록이 아니면 넣지 않는다
        if len(p) + 1 <= left:
            chosen.append(i)
            left -= len(p) + 1
    if not chosen:  # 문단 하나가 자리보다 크면(줄바꿈 없는 긴 글) 앞에서부터 자리만큼
        head = source[:room].strip()
        return (head, False) if len(head) >= MIN_LEFT else None
    return "\n".join(paras[i] for i in sorted(chosen)), False


def pick(section: dict, rule: Rule, room: int) -> Picked:
    """섹션 하나에서 rule대로 고른다. room은 이 섹션에 쓸 수 있는 글자 수(섹션 상한과 호출에 남은 자리 중 작은 쪽)."""
    blocks = split_blocks(section)
    total = len(section_text(section))
    excluded = [b for b in blocks if rule.exclude and any(k in norm(b.title) for k in rule.exclude)]
    blocks = [b for b in blocks if b not in excluded]
    budget = min(rule.limit, room)
    dropped = [b.title for b in excluded if b.title]
    whole = "\n\n".join(b.text for b in blocks)
    if len(whole) <= budget:
        return Picked(section["key"], section["label"], whole, total, [b.title for b in blocks if b.title], [], dropped)
    skipped: list[str] = []
    taken: dict[int, tuple[str, bool]] = {}
    left = budget
    order = sorted(blocks, key=lambda x: _rank(x, rule))
    n = len(rule.priority)
    for pos, b in enumerate(order):
        if left < MIN_LEFT:
            break
        if len(b.text) + 2 <= left:
            taken[b.index] = (b.text, True)
            left -= len(b.text) + 2
            continue
        # 큰 블록을 줄일 때는 뒤에 남은 우선순위 블록 자리(블록당 최대 RESERVE자)를 먼저 남겨 둔다
        # (LG전자 IV: 큰 '3. 재무상태 및 영업실적'이 '4. 유동성'을 밀어내지 않게)
        reserve = sum(min(len(x.text), RESERVE) for x in order[pos + 1:] if _rank(x, rule)[0] < n)
        part = _shrink(b, max(left - 2 - reserve, MIN_LEFT), rule)
        if part:
            taken[b.index] = part
            left -= len(part[0]) + 2
    used, out = [], []
    for b in blocks:
        if b.index in taken:
            text, full = taken[b.index]
            out.append(text)
            if b.title:
                used.append(b.title if full else f"{b.title} (일부)")
        elif b.title:
            skipped.append(b.title)
    return Picked(section["key"], section["label"], "\n\n".join(out), total, used, skipped, dropped)


def pick_many(items: list[tuple[dict, Rule]], call_limit: int = CALL_LIMIT) -> list[Picked]:
    """호출 하나에 넘길 섹션들을 앞에서부터(우선순위 순서로 넘겨 준다) 호출 상한 안에서 고른다."""
    out, left = [], call_limit
    for section, rule in items:
        if left < MIN_LEFT:
            break
        p = pick(section, rule, left)
        if p.text:
            out.append(p)
            left -= len(p.text)
    return out
