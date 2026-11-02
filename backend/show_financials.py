"""재무제표 확인용 출력 (개발용, spec에 없는 도구). 표준 항목 × 연도 표, 출처 링크, 매칭되지 않은 계정을 보여준다.

    backend/.venv/bin/python show_financials.py SK하이닉스
    backend/.venv/bin/python show_financials.py SK하이닉스 삼성전자 NAVER --ratios
    backend/.venv/bin/python show_financials.py SK하이닉스 --won        # 억 원 대신 원 단위 그대로 (원문 대조용)
    backend/.venv/bin/python show_financials.py SK하이닉스 --accounts   # 항목마다 어떤 DART 계정을 썼는지

DART 응답은 backend/data/dart_raw/ 에 저장해 같은 요청을 다시 보내지 않는다. 새로 보내는 호출만 0.5초 간격을 둔다.
"""
import argparse
import asyncio
import json
import sys

import httpx

from app.calc import analyze
from app.calc.models import Metric
from app.config import DATA_DIR
from app.dart import DartError
from app.fin_collect import ITEM_LABELS, NoFinancialsError, collect_company, to_year_list
from app.fin_fetch import FinancialsFetcher
from app.textfmt import table

PERCENT = {"operating_margin", "net_margin", "roe", "roa", "debt_ratio", "current_ratio",
           "revenue_growth", "operating_income_growth", "asset_growth"}
RATIO_LABELS = {
    "operating_margin": "영업이익률", "net_margin": "순이익률", "roe": "ROE", "roa": "ROA",
    "debt_ratio": "부채비율", "current_ratio": "유동비율", "interest_coverage": "이자보상배율",
    "asset_turnover": "총자산회전율", "receivable_turnover": "매출채권회전율", "inventory_turnover": "재고자산회전율",
    "revenue_growth": "매출액증가율", "operating_income_growth": "영업이익증가율", "asset_growth": "총자산증가율",
}


def resolve(name: str) -> tuple[str, str]:
    corps = json.loads((DATA_DIR / "listed_corps.json").read_text(encoding="utf-8"))["corps"]
    if name.isdigit() and len(name) == 8:
        return name, name
    hits = [c for c in corps if c["corp_name"].casefold() == name.casefold()]
    if len(hits) != 1:
        raise SystemExit(f"'{name}' 와 이름이 같은 상장 후보가 {len(hits)}곳입니다. 고유번호(8자리)로 지정해 주세요: "
                         + ", ".join(f'{h["corp_name"]}={h["corp_code"]}' for h in hits))
    return hits[0]["corp_code"], hits[0]["corp_name"]


def ratio_labels(res) -> dict[str, str]:
    """이자비용이 없어 금융비용으로 대체한 기업은 이자보상배율에 '금융비용 기준'을 붙인다."""
    labels = dict(RATIO_LABELS)
    if res.interest_basis() == "금융비용":
        labels["interest_coverage"] = "이자보상배율(금융비용 기준)"
    return labels


def money(v: float | None, won: bool) -> str:
    if v is None:
        return "-"
    return f"{v:,.0f}" if won else f"{v / 1e8:,.1f}"


def metric_text(key: str, m: Metric) -> str:
    if m.value is None:
        return (m.na_reason or "-").replace("해당 없음", "해당없음")
    text = f"{m.value * 100:.1f}%" if key in PERCENT else f"{m.value:.2f}배"
    return text + ("*" if m.year_end_only else "")


def print_company(name: str, res, years: list[int], args) -> None:
    unit = "원" if args.won else "억 원"
    print(f"\n{'=' * 70}\n{name}  ({res.corp_code})  기준: {res.basis}재무제표  사업연도 {years[0]}~{years[-1]}"
          f"  [{len(years)}년 자료{'만 있음' if len(years) < 5 else ''}]\n{'=' * 70}")
    for w in res.warnings:
        print(f"⚠ {w}")
    for n in res.notes:
        print(f"※ {n}")

    rows = [[ITEM_LABELS[f], *[money(getattr(res.years[y], f), args.won) for y in years]] for f in ITEM_LABELS]
    print(f"\n[표준 항목 × 연도]  단위: {unit}")
    print(table(["항목", *[str(y) for y in years]], rows))

    print("\n[출처: 연도별 사업보고서 접수번호와 DART 원문 링크]")
    for y in years:
        print(f"  {y}: {res.receipts[y]}  {res.source_link(y)}")

    if args.accounts:
        print("\n[항목별로 쓴 DART 계정 (최신 연도 기준)]")
        for f, label in ITEM_LABELS.items():
            u = res.used.get((res.latest_year, f))
            print(f"  {label}: " + (f'{u["sj_div"]} {u["account_nm"]} [{u["account_id"]}] ({"ID" if u["by"] == "id" else "이름"}로 매칭)' if u else "매칭 없음"))

    print("\n[매칭되지 않은 표준 항목]")
    any_missing = False
    for y in years:
        miss = res.missing.get(y, [])
        if miss:
            any_missing = True
            print(f"  {y}: " + ", ".join(ITEM_LABELS[f] for f in miss))
    if not any_missing:
        print("  없음 (모든 연도에서 17개 표준 항목이 모두 매칭됨)")
    for f, cands in res.candidates.items():
        print(f"  └ {ITEM_LABELS[f]} 후보 계정 ({res.latest_year}):" + ("" if cands else " 이름에 관련 키워드가 든 계정 없음"))
        for c in cands:
            print(f"      - {c}")

    if args.ratios:
        analysis = analyze(to_year_list(res))
        labels = ratio_labels(res)
        print("\n[5대 비율]  (* = 첫 연도라 평균 대신 기말 값 사용)")
        print(table(["지표", *[str(y) for y in years]],
                    [[labels[k], *[metric_text(k, analysis[y].ratios[k]) for y in years]] for k in labels]))
        if res.interest_basis() == "금융비용":
            print("  ※ 이자보상배율은 금융비용 기준입니다. 외환·파생상품 손실이 포함될 수 있어 실제 이자비용 기준과 크게 다를 수 있습니다.")
        print("\n[듀퐁 (지배주주 기준)]")
        dk = [("net_margin", "순이익률"), ("asset_turnover", "총자산회전율"), ("leverage", "재무레버리지"), ("roe", "ROE")]
        print(table(["요소", *[str(y) for y in years]],
                    [[label, *[metric_text("roe" if k == "roe" else "asset_turnover" if k != "net_margin" else "net_margin",
                                          analysis[y].dupont[k]) if k != "leverage" else
                               (f"{analysis[y].dupont[k].value:.2f}배" if analysis[y].dupont[k].value is not None else "-")
                               for y in years]] for k, label in dk]))
        print("  ROE 변화 주된 이유: " + ", ".join(
            f"{y}: {analysis[y].dupont_driver.factor}" if analysis[y].dupont_driver else f"{y}: -" for y in years))
        print("\n[현금흐름 패턴]  " + ", ".join(f"{y}: {analysis[y].cashflow_pattern or '-'}" for y in years))
        print("[신호등]")
        sig_names = {"revenue_growth": "매출 성장률", "operating_margin": "영업이익률",
                     "debt_ratio": "부채비율", "operating_cashflow": "영업현금흐름"}
        print(table(["지표", *[str(y) for y in years]],
                    [[sig_names[k], *[(analysis[y].signals[k].level if analysis[y].signals[k] else "-") for y in years]]
                     for k in sig_names]))


async def main() -> int:
    parser = argparse.ArgumentParser(description="재무제표 수집 결과(표준 항목 × 연도)를 확인용으로 출력합니다.")
    parser.add_argument("companies", nargs="+", help="기업명(상장 정확히 일치) 또는 8자리 고유번호")
    parser.add_argument("--won", action="store_true", help="억 원 대신 원 단위 그대로 출력")
    parser.add_argument("--ratios", action="store_true", help="계산 결과(비율·듀퐁·현금흐름 패턴·신호등)도 출력")
    parser.add_argument("--accounts", action="store_true", help="항목마다 쓴 DART 계정을 출력")
    args = parser.parse_args()
    targets = [resolve(c) for c in args.companies]
    async with httpx.AsyncClient() as client:
        fetcher = FinancialsFetcher(client)
        for corp_code, name in targets:
            try:
                res = await collect_company(fetcher, corp_code)
            except (DartError, NoFinancialsError) as e:
                print(f"\n{name}: 수집 실패 — {e}")
                return 1
            print_company(name, res, sorted(res.years), args)
        print(f"\n(이번 실행에서 DART에 실제로 보낸 호출: {fetcher.calls_made}건, 나머지는 저장본 사용)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
