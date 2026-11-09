#!/bin/bash
# 결과 확인용: 실제 OpenAI 호출 및 웹 검색(작업별 최대 3번, 비용 발생). 생성 도중 끊기지 않게 --reload는 쓰지 않는다
echo "실제 AI 모드입니다. 리포트를 만들 때마다 비용이 나갑니다. (끄기: Ctrl+C)"
echo "웹 검색(실적 기사 + 누락된 사업 매출 정보): ${WEB_NEWS:-1} (1=켬, 끄려면 WEB_NEWS=0 ./run-live.sh)"
cd "$(dirname "$0")" && LLM_PROVIDER=openai LLM_ALLOW_LIVE=1 .venv/bin/python -m uvicorn app.main:app --port 8000
