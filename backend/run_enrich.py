"""공시 확인·AI 해석 실행 도구 (개발용, 터미널에서 실행). 이미 만든 작업은 다시 만들지 않는다.

    LLM_PROVIDER=fake backend/.venv/bin/python run_enrich.py 8            # 가짜 응답(외부 AI 호출 없음)
    backend/.venv/bin/python run_enrich.py 8 --reset                      # 이 리포트의 저장된 결과를 지우고 처음부터 (실제 호출은 LLM_ALLOW_LIVE=1일 때만)
    backend/.venv/bin/python run_enrich.py 8 --only write_swot,write_page4  # 이 작업만 지우고 다시 만든다 (지시문을 고친 뒤 비용을 아끼려고)

작업별 결과와 실제 사용 토큰 수를 보여준다. 키 값은 출력하지 않는다.
"""
import argparse
import asyncio
import sys

from app import db
from app.enrich import TASKS, enrich_report
from app.report_models import Enrichment
from show_costs import cost_usd


async def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_id", type=int)
    parser.add_argument("--reset", action="store_true", help="저장된 공시 확인·AI 결과를 지우고 처음부터 만든다")
    parser.add_argument("--only", help="쉼표로 나눈 작업 이름. 이 작업만 지우고 다시 만든다 (이름은 인자 없이 실행한 결과 왼쪽 열)")
    args = parser.parse_args(argv)
    db.ensure_init()
    if args.only:
        keys = [k.strip() for k in args.only.split(",") if k.strip()]
        unknown = [k for k in keys if k not in TASKS]
        if unknown:
            print(f"없는 작업 이름: {', '.join(unknown)}\n가능한 이름: {', '.join(TASKS)}")
            return 2
        with db.SessionLocal() as s:
            s.query(Enrichment).filter(Enrichment.report_id == args.report_id, Enrichment.key.in_(keys)).delete(synchronize_session=False)
            s.commit()
    elif args.reset:
        with db.SessionLocal() as s:
            s.query(Enrichment).filter_by(report_id=args.report_id).delete()
            s.commit()
    await enrich_report(args.report_id, asyncio.Lock())
    with db.SessionLocal() as s:
        rows = {e.key: e for e in s.query(Enrichment).filter_by(report_id=args.report_id)}
    total_in = total_out = calls = 0
    usd = 0.0
    for key in TASKS:
        e = rows.get(key)
        if e is None:
            print(f"{key:18} (없음)")
            continue
        usage = f"{e.input_tokens:>7,} / {e.output_tokens:>6,}" if e.by == "ai" else "      -"
        print(f"{key:18} {e.status:7} {e.model or '-':14} 토큰(입력/출력) {usage}  {e.message or ''}")
        for w in e.warnings or []:
            print(f"{'':18}   ⚠ {w}")
        if e.by == "ai" and e.model and e.model != "fake":
            calls += 1
            total_in += e.input_tokens
            total_out += e.output_tokens
            usd += cost_usd(e.model, e.input_tokens, e.output_tokens)
    print(f"\n실제 AI 호출 {calls}회, 입력 {total_in:,} 토큰, 출력 {total_out:,} 토큰, 예상 ${usd:.3f} (약 {usd * 1400:,.0f}원, 가짜 응답은 0회)")
    return 0 if all(r.status != "failed" for r in rows.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
