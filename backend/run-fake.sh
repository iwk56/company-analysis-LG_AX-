#!/bin/bash
# 평소 작업: 가짜 응답(AI 비용 0원), 코드를 고치면 서버가 자동으로 다시 시작
cd "$(dirname "$0")" && LLM_PROVIDER=fake LLM_ALLOW_LIVE=0 .venv/bin/python -m uvicorn app.main:app --port 8000 --reload
