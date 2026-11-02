"""터미널 표 출력용: 한글(전각)은 2칸으로 세어 열을 맞춘다."""
import unicodedata


def width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def pad(text: str, w: int, right: bool = False) -> str:
    gap = " " * (w - width(text))
    return gap + text if right else text + gap


def table(header: list[str], rows: list[list[str]], right_from: int = 1) -> str:
    """첫 열부터 right_from 전까지는 왼쪽, 이후 열은 오른쪽 정렬."""
    all_rows = [header] + rows
    widths = [max(width(r[i]) for r in all_rows) for i in range(len(header))]
    def line(r):
        return "  ".join(pad(c, widths[i], right=i >= right_from) for i, c in enumerate(r)).rstrip()
    return "\n".join([line(header), "  ".join("-" * w for w in widths)] + [line(r) for r in rows])
