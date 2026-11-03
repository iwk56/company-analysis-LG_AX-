// 네이버 검색결과 문자열(제목·요약문)을 안전하게 표시하기 위한 변환.
// 약관상 받은 그대로 보여줘야 하므로 검색어 강조 <b>…</b>는 지우지 않고 굵은 글씨로 바꾼다.
// HTML로 끼워 넣지 않고(dangerouslySetInnerHTML 금지) 글자 조각으로 나눠 React가 글자로만 그리게 한다.
// <b>, </b> 외의 태그는 해석하지 않고 글자 그대로 보인다.

export interface TextPart {
  text: string
  bold: boolean
}

const NAMED: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' }

/** HTML 문자(&quot; &#39; &#x27; 등)를 원래 글자로 바꾼다. 모르는 이름은 그대로 둔다. */
export function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (whole, code: string) => {
    if (code[0] === '#') {
      const n = code[1] === 'x' || code[1] === 'X' ? parseInt(code.slice(2), 16) : parseInt(code.slice(1), 10)
      return Number.isFinite(n) && n > 0 && n <= 0x10ffff ? String.fromCodePoint(n) : whole
    }
    return NAMED[code.toLowerCase()] ?? whole
  })
}

/** "<b>SK하이닉스</b> 실적" → [{text:'SK하이닉스', bold:true}, {text:' 실적', bold:false}] */
export function naverParts(raw: string): TextPart[] {
  const parts: TextPart[] = []
  let bold = false
  for (const piece of raw.split(/(<\/?b>)/i)) {
    const tag = piece.toLowerCase()
    if (tag === '<b>') bold = true
    else if (tag === '</b>') bold = false
    else if (piece) {
      const text = decodeEntities(piece)
      const last = parts[parts.length - 1]
      if (last && last.bold === bold) last.text += text
      else parts.push({ text, bold })
    }
  }
  return parts
}
