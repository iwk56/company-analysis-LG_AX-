"""리포트별 실제 AI 호출 수·토큰·예상 비용 (개발용, 터미널에서 실행). DB에 저장된 값만 읽고 외부 호출은 하지 않는다.

    backend/.venv/bin/python show_costs.py        # 리포트별 합계
    backend/.venv/bin/python show_costs.py 12     # 이 리포트의 작업별 내역

가격은 docs/progress.md에 기록한 100만 토큰당 가격(USD). 바뀌면 PRICES만 고친다. 원화는 1달러 = 1,400원으로 어림한다.
"""
import sys
from collections import defaultdict

PRICES = {"gpt-6-sol": (2.0, 10.0), "gpt-6-luna": (0.10, 0.50)}  # (입력, 출력) 100만 토큰당 USD
KRW = 1400
SEARCH_FEE = 0.01  # 웹 검색 도구 요금 어림값(검색 1번당 USD). 실제 단가는 OpenAI 가격표 기준으로 바뀌면 고친다


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    price = PRICES.get(model or "")
    if not price:
        return 0.0
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000


def main(argv: list[str]) -> int:
    from app import db
    from app.report_models import Company, Enrichment, Report

    db.ensure_init()
    with db.SessionLocal() as s:
        q = s.query(Enrichment).filter(Enrichment.by == "ai", Enrichment.model.isnot(None), Enrichment.model != "fake")
        if argv:
            rid = int(argv[0])
            total = 0.0
            for e in q.filter(Enrichment.report_id == rid).order_by(Enrichment.id):
                c = cost_usd(e.model, e.input_tokens, e.output_tokens) + SEARCH_FEE * int((e.content or {}).get("searches") or 0)
                total += c
                print(f"{e.key:18} {e.status:7} {e.model:12} {e.input_tokens:>7,} / {e.output_tokens:>6,}  ${c:.4f}")
            print(f"\n리포트 {rid}: ${total:.3f} (약 {total * KRW:,.0f}원)")
            return 0
        names = {rid: name for rid, name in s.query(Report.id, Company.corp_name).join(Company, Company.corp_code == Report.corp_code)}
        rows = defaultdict(lambda: [0, 0, 0, 0.0])
        for e in q:
            r = rows[e.report_id]
            r[0] += 1
            r[1] += e.input_tokens
            r[2] += e.output_tokens
            r[3] += cost_usd(e.model, e.input_tokens, e.output_tokens) + SEARCH_FEE * int((e.content or {}).get("searches") or 0)
    if not rows:
        print("아직 실제 AI 호출이 없습니다 (가짜 응답만 있음)")
        return 0
    grand = 0.0
    print(f"{'리포트':>6}  {'기업':10} {'호출':>4} {'입력 토큰':>10} {'출력 토큰':>9}  비용")
    for rid in sorted(rows):
        n, i, o, c = rows[rid]
        grand += c
        print(f"{rid:>6}  {names.get(rid, ''):10} {n:>4} {i:>10,} {o:>9,}  ${c:.3f}")
    print(f"\n합계 ${grand:.3f} (약 {grand * KRW:,.0f}원)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
