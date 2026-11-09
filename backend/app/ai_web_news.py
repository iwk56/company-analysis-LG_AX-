"""실적 변화의 외부 원인을 웹 기사로 찾기 (2026-11-04, 실적 탭 '왜 이렇게 됐나'). AI 웹 검색 1회 호출(검색 최대 3번).

- 넘기는 자료: 손익 단계표·영업이익 변화 분해(코드), 제품별 매출 증감, 주석에서 증감이 큰 항목(코드). 네이버 기사는 넘기지 않는다(약관).
- AI는 단계(매출·매출총이익률·판관비·영업외손익)마다 그 변화를 설명하는 기사 속 사실을 1~2문장으로 자기 말로 쓰고 기사 주소를 붙인다.
- price(주력 제품 가격 동향)는 손익 단계와 상관없이, 사업보고서에 안 나오는 "가격이 오르는지 내리는지"를 기사로 보완하는 용도
  (2026-11-05, 사업 구조 탭 "무엇을 파나" 아래에도 같이 보여 준다). 새 AI 호출을 늘리지 않고 같은 검색 결과에서 분류만 더 한다.
- 코드 확인: 기사 주소가 모델이 실제로 검색·인용한 주소 목록에 없으면 버린다(지어낸 링크 방지). 단계 키·문장 길이도 확인한다.
- 기사 속 숫자는 우리 자료로 검증할 수 없어 화면에 '기사 내용'으로 구분하고 링크를 단다. 투자 권유 문장은 쓰지 않게 한다.
- WEB_NEWS=0이면 호출하지 않는다.
"""
import httpx

from . import ai_prompts as P
from .ai_facts import Facts
from .ai_income import note_lines
from .ai_tasks import Outcome
from .config import web_news_enabled
from .llm import LlmError, call_web_json, _strip_utm

STEPS = ("revenue", "gross", "sga", "non_operating", "price")
MAX_ITEMS = 8


def _top_product(facts: Facts) -> str | None:
    """제품별 매출 자료의 첫 제품 이름(가장 큰 것). 없으면 None."""
    seg = facts.blocks.get("segments") or ""
    for line in seg.splitlines()[1:]:
        name = line.split(":")[0].strip()
        if name:
            return name
    return None


async def find_web_news(client: httpx.AsyncClient, report: dict, facts: Facts, notes: dict) -> Outcome:
    if not web_news_enabled():
        return Outcome("empty", message="웹 검색이 꺼져 있습니다 (WEB_NEWS=0)")
    if "income" not in facts.blocks:
        return Outcome("empty", message="손익계산서 자료가 없어 웹 검색을 하지 않았습니다")
    c = report["company"]
    y, name = report["base_year"], c["corp_name"]
    top = _top_product(facts)
    queries = [f"{name} {y}년 실적 영업이익 증가 이유", f"{top} 가격 {y}년" if top else f"{name} 주력 제품 업황 {y}년",
               f"{name} {y}년 4분기 실적 발표"]
    parts = {"분석 기업": f"{name} (업종: {c.get('industry_name') or '모름'}), 기준 사업연도 {y}",
             "추천 검색어": "\n".join(queries),
             "손익 변화 (코드 계산)": facts.blocks["income"]}
    if "segments" in facts.blocks:
        parts["제품별 매출"] = facts.blocks["segments"]
    for k, title in (("sga", "판관비 주석"), ("finance", "금융손익 주석"), ("other", "기타영업외 주석")):
        if notes.get(k):
            parts[title] = note_lines(notes[k])
    try:
        r = await call_web_json(client, "web_news", P.WEB_RULES, P.user_message(P.WEB_NEWS, parts))
    except LlmError as e:
        return Outcome("failed", message=e.message)
    items, dropped = [], []
    for i, x in enumerate(r.data.get("items") if isinstance(r.data.get("items"), list) else []):
        if not isinstance(x, dict) or len(items) >= MAX_ITEMS:
            continue
        url = _strip_utm(str(x.get("url") or ""))
        step, claim = x.get("step"), str(x.get("claim") or "").strip()
        if step not in STEPS or not claim or len(claim) > 300:
            dropped.append(f"기사 {i + 1}: 단계 이름이 틀리거나 문장이 비었음")
            continue
        if not url.startswith("http") or url not in r.cited:
            dropped.append(f"기사 {i + 1}: 실제 검색 결과에 없는 주소라 버림")
            continue
        items.append({"step": step, "claim": claim, "title": str(x.get("title") or "")[:120], "publisher": str(x.get("publisher") or "")[:40],
                      "date": str(x.get("date") or "")[:10], "url": url})
    if not items:  # 원인을 보려고 응답 모양을 남긴다(기사 내용은 남기지 않음)
        dropped.append(f"응답 키 {sorted(r.data)[:5]}, 항목 {len(r.data.get('items') or []) if isinstance(r.data.get('items'), list) else '없음'}개, 인용 주소 {len(r.cited)}개")
    # 기사를 못 찾으면 failed로 남겨 [AI 다시 실행] 때 다시 찾게 한다(검색 비용 기록은 content에 남김)
    o = Outcome("ok" if items else "failed", {"items": items, "searches": r.searches},
                message=None if items else f"실적 변화를 설명하는 기사를 찾지 못했습니다 (검색 {r.searches}번)", warnings=dropped)
    o.model, o.input_tokens, o.output_tokens = r.model, r.input_tokens, r.output_tokens
    return o
