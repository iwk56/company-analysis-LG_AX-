"""뉴스 검색어 미리보기 (개발용, 터미널에서 실행). 저장하지 않고 화면에 헤드라인만 찍는다. AI는 부르지 않는다.

    backend/.venv/bin/python preview_news.py SK하이닉스 LG전자 아모레퍼시픽 카카오
    backend/.venv/bin/python preview_news.py 현대차 --topics "{name} 사업" "{name} 출시"   # 검색어 틀을 직접 시험

업종이 달라도 주제별 검색어(news.TOPICS)가 쓸 만한 기사를 가져오는지 보려는 도구다. 결과는 저장하지 않는다(약관상 보관 문제 없음).
"""
import argparse
import asyncio
import re
import sys

import httpx

from app.news import TOPIC_DISPLAY, TOPIC_SORT, TOPICS, fetch_news


def plain(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).replace("&quot;", '"').replace("&amp;", "&").replace("&#39;", "'")


async def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("names", nargs="+", help="회사 이름(검색에 쓰는 이름)")
    p.add_argument("--topics", nargs="+", help='검색어 틀. 예: "{name} 사업" (없으면 news.TOPICS)')
    args = p.parse_args(argv)
    topics = [(t, t) for t in args.topics] if args.topics else list(TOPICS)
    async with httpx.AsyncClient() as client:
        for name in args.names:
            print(f"\n==================== {name}")
            for label, tpl in topics:
                q = tpl.format(name=name)
                items = await fetch_news(client, q, display=TOPIC_DISPLAY, sort=TOPIC_SORT)
                print(f"\n[{label}] {q}")
                for it in items:
                    print(f"  - {it['published_at']:%m.%d} {plain(it['title'])[:60]}")
                if not items:
                    print("  (검색결과 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
