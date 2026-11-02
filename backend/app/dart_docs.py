"""사업보고서 원문(OpenDART document.xml) 수집과 절 단위 텍스트 추출.

원문 zip은 `data/dart_docs/{접수번호}.zip`에 저장해 같은 문서를 다시 받지 않는다. 문서 안에는 사업보고서 본문(접수번호.xml)과
감사보고서 등이 함께 들어 있고, 본문은 접수번호와 이름이 같은 파일이다.
"""
import io
import re
import zipfile
from html import unescape

import httpx

from .config import DATA_DIR
from .dart import DartError, _get

DOCS_DIR = DATA_DIR / "dart_docs"


async def load_document_zip(client: httpx.AsyncClient, rcept_no: str, docs_dir=DOCS_DIR) -> bytes:
    path = docs_dir / f"{rcept_no}.zip"
    if path.exists():
        return path.read_bytes()
    resp = await _get(client, "document.xml", {"rcept_no": rcept_no})
    if not resp.content.startswith(b"PK"):  # 오류 시 zip이 아닌 XML이 온다
        raise DartError("document", "공시 원문을 받지 못했습니다")
    docs_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return resp.content


def main_document(zip_bytes: bytes, rcept_no: str) -> str:
    """zip 안에서 사업보고서 본문(접수번호와 같은 이름의 파일) XML 문자열."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        name = f"{rcept_no}.xml"
        if name not in z.namelist():
            raise DartError("document", "공시 원문에서 본문 파일을 찾지 못했습니다")
        return z.read(name).decode("utf-8", errors="replace")


_SECTION = re.compile(r"<(SECTION-\d)[^>]*>\s*<TITLE[^>]*>(.*?)</TITLE>", re.S)
_CELL_END = re.compile(r"</(TD|TH|TE|TU)>", re.I)
_ROW_END = re.compile(r"</TR>", re.I)
_BLOCK_END = re.compile(r"</(P|TITLE|SECTION-\d|TABLE)>", re.I)
_TAG = re.compile(r"<[^>]+>")


def to_text(xml: str) -> str:
    """태그를 걷어낸 평문. 표의 칸은 ' | ', 표의 한 행은 한 줄로 남긴다."""
    xml = re.sub(r"[\r\n]+", " ", xml)  # 원문의 서식용 줄바꿈은 버리고, 아래 표지로만 줄을 나눈다
    xml = _CELL_END.sub(" | ", xml)
    xml = _ROW_END.sub("\n", xml)
    xml = _BLOCK_END.sub("\n", xml)
    text = unescape(_TAG.sub("", xml)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t　]+", " ", ln).strip(" |") .strip() for ln in text.splitlines())
    return "\n".join(ln for ln in lines if ln)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def section_text(xml: str, title: str, level: str = "SECTION-2", occurrence: int = 1) -> str | None:
    """제목이 title과 같은(공백 무시) level 절의 평문. 같은 제목이 여러 개면 occurrence번째. 없으면 None."""
    heads = [(m.start(), m.group(1), _norm(unescape(_TAG.sub("", m.group(2))))) for m in _SECTION.finditer(xml)]
    want = _norm(title)
    seen = 0
    for i, (start, lvl, name) in enumerate(heads):
        if lvl != level or name != want:
            continue
        seen += 1
        if seen < occurrence:
            continue
        rank = int(level[-1])
        end = next((s for s, l, _ in heads[i + 1:] if int(l[-1]) <= rank), len(xml))
        return to_text(xml[start:end])
    return None


def find_section(xml: str, keyword: str, level: str = "SECTION-2") -> str | None:
    """제목에 keyword가 들어간(공백 무시) 첫 level 절의 평문. 없으면 None."""
    want = _norm(keyword)
    for m in _SECTION.finditer(xml):
        if m.group(1) == level:
            name = _norm(unescape(_TAG.sub("", m.group(2))))
            if want in name:
                return section_text(xml, name, level)
    return None


def note_text(notes: str, keyword: str) -> str | None:
    """주석 평문에서 번호 제목에 keyword가 든 주석 하나(다음 번호 제목 직전까지). 없으면 None."""
    lines = notes.splitlines()
    want = _norm(keyword)
    for i, ln in enumerate(lines):
        m = re.match(r"^(\d+)\. ", ln)
        if m and want in _norm(ln):
            nxt = f"{int(m.group(1)) + 1}. "
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith(nxt)), len(lines))
            return "\n".join(lines[i:end])
    return None


def financial_notes(xml: str) -> str | None:
    """연결재무제표 주석(없으면 재무제표 주석) 절의 평문."""
    return find_section(xml, "연결재무제표주석") or find_section(xml, "재무제표주석")
