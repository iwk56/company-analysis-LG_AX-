"""기사만 다시 받기 (개발용, 터미널에서 실행). AI는 부르지 않고 네이버 뉴스 검색만 4번 한다(주제별 검색어 × 5건).

    backend/.venv/bin/python run_news.py 13

리포트의 기사 검색 기록과 기사를 새로 받은 것으로 바꾼다(약관상 보관 21일은 새 수집일부터 다시 센다). 키 값은 출력하지 않는다.
"""
import asyncio
import sys

import httpx

from app import db, report_store
from app.jobs import collect_news
from app.report_models import Report


async def main(argv: list[str]) -> int:
    if not argv:
        print("사용법: run_news.py 리포트번호")
        return 2
    rid = int(argv[0])
    db.ensure_init()
    with db.SessionLocal() as s:
        report = s.get(Report, rid)
        if report is None:
            print(f"리포트 {rid}이(가) 없습니다")
            return 1
        name = report.company.corp_name
    async with httpx.AsyncClient() as client:
        news = await collect_news(client, name)
    with db.SessionLocal() as s:
        report_store.replace_articles(s, rid, news)
        view = report_store.get_report(s, rid)["articles"]
    for g in view["groups"]:
        print(f"{g['label'] or '전체'} ({g['query']}): {len(g['items'])}건")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
