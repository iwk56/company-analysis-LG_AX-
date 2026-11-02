"""AI에게 주는 지시문. 모든 작업에 같은 규칙(넘겨준 자료 안에서만, 숫자 만들지 않기, 근거 없으면 자료 없음)을 붙인다."""

RULES = """당신은 한국 상장기업 분석 리포트를 돕는 보조자입니다. 아래 규칙을 반드시 지킵니다.
1. [자료] 안에 있는 내용만 사용합니다. 자료에 없는 사실·숫자·전망을 만들지 않습니다. 근거가 없으면 null 또는 "자료 없음"이라고 씁니다.
2. 숫자를 새로 계산하지 않습니다(합계·차이·비율·평균 계산 금지). 자료에 적힌 숫자를 적힌 그대로만 인용합니다.
3. 투자 권유나 주가 전망은 쓰지 않습니다.
4. JSON 객체 하나만 출력합니다. 설명 문장이나 코드 울타리를 붙이지 않습니다."""

EXTRACT_SEGMENTS = """[할 일] 자료에서 (가) 제품·사업부문별 매출액과 (나) 지역별 매출액의 국내 금액을 찾아 JSON으로 돌려주세요.
- 값은 표에 적힌 문자열 그대로(쉼표 포함) 옮깁니다. 단위 환산이나 합계 계산을 하지 않습니다.
- products: 가장 세분된 제품·사업부문별 매출 행(합계 열 제외). current는 가장 최근 기(당기), prior는 그 직전 기(전기)의 값입니다. 전기 값이 없으면 prior는 null.
- products_quote_current / products_quote_prior: 위 값들이 들어 있는 원문 부분을 머리글 행과 값 행까지 한 덩어리로 자료에서 그대로 복사한 문자열.
- unit: 표의 금액 단위(예: 백만원). unit_quote: 단위가 적힌 원문 부분을 그대로 복사(예: "당기 | (단위 : 백만원)").
- region: 지역별 매출표에서 domestic(국내 매출액), total(지역 합계), quote(두 값이 든 값 행을 그대로 복사). 당기 값만. 없으면 null.
- 자료에 해당 표가 없으면 products는 빈 목록, region은 null로 둡니다.
출력 형식:
{"unit": "", "unit_quote": "", "products": [{"name": "", "current": "", "prior": ""}], "products_quote_current": "", "products_quote_prior": "",
 "region": {"domestic": "", "total": "", "quote": ""} }"""

EXTRACT_RND = """[할 일] 자료에서 가장 최근 기(당기)의 연구개발비용 합계 금액을 찾아 JSON으로 돌려주세요.
- amount: 표에 적힌 문자열 그대로(쉼표 포함). 가장 왼쪽 열이 보통 당기입니다. 환산·계산 금지.
- quote: amount가 들어 있는 행을 자료에서 그대로 복사한 문자열. unit / unit_quote: 단위(예: 백만원)와 그것이 적힌 원문 부분(예: "(단위: 백만원)").
- 연구개발비를 찾을 수 없으면 amount는 null.
출력 형식: {"amount": "", "quote": "", "unit": "", "unit_quote": ""}"""

EXTRACT_FINANCE = """[할 일] 자료에서 아래를 찾아 JSON으로 돌려주세요. 값은 표에 적힌 문자열 그대로(쉼표 포함)이며 환산·계산 금지입니다.
1. interest_expense: [연간 주석]의 금융비용 표에서 당기 이자비용(이자비용 행, 당기 열). quote는 그 행을 그대로 복사, unit / unit_quote는 단위와 그것이 적힌 원문 부분(예: "당기 | (단위 : 백만원)"). 없으면 null.
2. finance_income_items: 요청이 있을 때만(아래 [요청] 참고). 해당 기간 누적 금융수익 표의 금액이 큰 항목 최대 5개. 항목마다 label, value, quote(그 행 그대로), unit, unit_quote. 금융수익 소계 행은 제외합니다.
출력 형식:
{"interest_expense": {"value": "", "quote": "", "unit": "", "unit_quote": ""},
 "finance_income_items": [{"label": "", "value": "", "quote": "", "unit": "", "unit_quote": ""}]}"""

WRITE_OVERVIEW = """[할 일] [자료]만 보고 아래 JSON을 만드세요. 쉬운 말로 씁니다.
- overview: 이 회사가 무엇을 하는 회사인지 2~3문장. 업종과 자료에 있는 사실만 씁니다.
- bcg: 사업부문(품목)별 비중과 전년 대비 증감률을 보고 어느 부문이 매출의 중심이고 어느 부문이 빠르게 늘거나 줄었는지 해석합니다.
  summary는 2~3문장, segments는 부문마다 comment 1문장. 시장점유율 자료가 없으므로 BCG 매트릭스의 4칸 이름(스타·캐시카우 등)을 단정하지 말고 '비중과 성장 속도' 관점으로만 씁니다.
  사업부문 자료가 없으면 bcg는 null.
- 숫자는 [자료]에 적힌 것만 그대로 쓰고, 새로 계산하지 않습니다.
출력 형식: {"overview": "", "bcg": {"summary": "", "segments": [{"name": "", "comment": ""}]}}"""

SUMMARY_KEYS = [("core_cards", "핵심 지표 카드"), ("recent_results", "최근 실적"), ("trend", "실적 추이"), ("ratios", "재무비율"),
                ("dupont", "듀퐁 분석"), ("cashflow", "현금흐름 패턴"), ("competitors", "경쟁사 비교"), ("segments", "사업부문 비중")]
NOTE_KEYS = [("revenue_growth", "매출 성장률"), ("operating_margin", "영업이익률"), ("net_margin", "순이익률"), ("roe", "ROE"),
             ("debt_ratio", "부채비율"), ("current_ratio", "유동비율"), ("interest_coverage", "이자보상배율"),
             ("asset_turnover", "총자산회전율"), ("operating_cashflow", "영업현금흐름"), ("cashflow_pattern", "현금흐름 패턴")]
NET_VS_OPERATING_NOTE = ("net_vs_operating", "순이익이 영업이익보다 큰 이유 (영업외 항목)")

WRITE_SUMMARIES = """[할 일] [자료]만 보고 섹션별 한 줄 요약과 지표 주석을 JSON으로 만드세요. 쉬운 말로 씁니다.
- summaries: 요청한 섹션마다 한 줄(80자 안팎). 이 회사 상황에서 가장 눈에 띄는 점 하나를 씁니다.
- notes: 요청한 지표마다 meaning(이 지표가 무엇인지 쉬운 말 1문장, 숫자 없이)과 why(이 회사 상황에서 왜 중요한지 1~2문장, 자료의 숫자를 인용).
  이자보상배율이 금융비용으로 계산된 값이면 why에 그 한계를 한 번 언급합니다.
- 자료에 없는 섹션·지표는 해당 키를 아예 빼거나 null로 둡니다.
출력 형식: {"summaries": {"<섹션 키>": ""}, "notes": {"<지표 키>": {"meaning": "", "why": ""}}}"""


def user_message(task_text: str, sources: dict[str, str], request: str = "") -> str:
    parts = [task_text]
    if request:
        parts.append(f"[요청]\n{request}")
    parts += [f"[자료] {title}\n{body}" for title, body in sources.items()]
    return "\n\n".join(parts)


# ───────────────────────── 6-B 회계 이슈
EXTRACT_GOING_CONCERN = """[할 일] [자료]의 '회계감사인의 명칭 및 감사의견' 표(및 있으면 주석 단락)를 보고, 가장 최근 기(당기)의 감사보고서에서 '계속기업 관련 중요한 불확실성'이 있다고 보고되었는지 판단해 JSON으로 돌려주세요.
- has_material_uncertainty: 당기 행(별도·연결 중 하나라도)에 중요한 불확실성이 '있다'고 적혀 있으면 true, '해당사항 없음'이면 false, 자료만으로 판단할 수 없으면 null.
  '계속기업'이라는 단어가 자본관리 정책 같은 일반 설명에 나오는 것만으로는 true가 아닙니다.
- quote: 판단의 근거가 된 당기 행(또는 문장)을 자료에서 그대로 복사한 문자열. 지어내지 않습니다.
출력 형식: {"has_material_uncertainty": false, "quote": ""}"""

EXTRACT_RELATED_PARTY = """[할 일] [자료]는 연결재무제표 주석의 특수관계자 주석입니다. 가장 최근 기(당기)의 아래 항목을 찾아 JSON으로 돌려주세요. 값은 표에 적힌 문자열 그대로(쉼표 포함)이며 환산·계산·합산 금지입니다.
1. sales_total: 특수관계자 거래 표 '매출 등' 행의 합계 열 값(보통 행의 맨 오른쪽 칸). quote는 그 행 전체를 그대로 복사.
2. purchases_total: '매입 등' 행의 합계 열 값. quote는 그 행 전체를 그대로 복사.
3. unit / unit_quote: 그 표의 금액 단위(예: 백만원)와 그것이 적힌 원문 부분(예: "당기 | (단위 : 백만원)").
4. top_transactions: 당기 거래 표에서 금액이 큰 특수관계자별 매출 등·매입 등 거래 최대 5개(합계 열과 '기타' 열 제외). 항목마다 party(표에 적힌 회사명 그대로), kind("매출 등" 또는 "매입 등"), value, quote(그 값이 든 행 전체를 그대로 복사).
5. loans: 특수관계자에 대한 자금 대여금(빌려준 돈) 금액. 항목마다 party, amount_text(원문에 적힌 금액 표기 그대로, 예: "5,000" 또는 "RMB 701백만"), quote(그 금액이 든 행이나 문장을 그대로 복사). 없으면 빈 목록.
6. guarantees: 특수관계자를 위해 제공한 지급보증(보증) 금액. loans와 같은 형식. 없으면 빈 목록.
- 찾을 수 없는 항목은 null 또는 빈 목록으로 둡니다. 전기 값을 당기로 옮기지 않습니다.
출력 형식:
{"unit": "", "unit_quote": "", "sales_total": {"value": "", "quote": ""}, "purchases_total": {"value": "", "quote": ""},
 "top_transactions": [{"party": "", "kind": "", "value": "", "quote": ""}],
 "loans": [{"party": "", "amount_text": "", "quote": ""}], "guarantees": [{"party": "", "amount_text": "", "quote": ""}]}"""

ACCOUNTING_NOTE_KEYS = [("audit_opinion", "감사의견"), ("going_concern", "계속기업 불확실성"), ("corrections", "정정공시"), ("related_party", "특수관계자 거래")]

WRITE_ACCOUNTING = """[할 일] [자료]만 보고 회계 이슈 체크리스트의 한 줄 요약과 항목별 주석을 JSON으로 만드세요. 쉬운 말로 씁니다. 판정(이상 없음·확인 필요·확인 불가)은 자료에 적힌 대로만 쓰고 바꾸지 않습니다.
- summary: 네 항목 전체를 한 줄(80자 안팎)로. '확인 필요'나 '확인 불가'가 있으면 그것을 먼저 언급합니다.
- notes: 요청한 항목마다 meaning(이 항목이 무엇인지 쉬운 말 1문장, 숫자 없이)과 why(이 회사 결과를 반영해 왜 중요한지 1~2문장, 자료의 숫자만 인용).
  특수관계자 거래의 30% 기준은 이 도구의 참고 기준일 뿐 법적 기준이 아니라고 why에 한 번 언급합니다.
- 확인 불가인 항목은 notes에서 해당 키를 빼도 됩니다. 법적 위반이나 부정을 단정하지 않습니다.
출력 형식: {"summary": "", "notes": {"<항목 키>": {"meaning": "", "why": ""}}}"""
