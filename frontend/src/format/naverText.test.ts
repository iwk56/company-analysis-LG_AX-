import { describe, expect, it } from 'vitest'
import { decodeEntities, naverParts } from './naverText'

describe('naverParts', () => {
  it('<b>만 굵은 글씨 조각으로 바꾼다', () => {
    expect(naverParts('<b>SK하이닉스</b> 실적')).toEqual([
      { text: 'SK하이닉스', bold: true },
      { text: ' 실적', bold: false },
    ])
  })
  it('대문자 <B>도 같다', () => {
    expect(naverParts('a <B>b</B>')).toEqual([
      { text: 'a ', bold: false },
      { text: 'b', bold: true },
    ])
  })
  it('다른 태그는 해석하지 않고 글자 그대로 둔다', () => {
    expect(naverParts('<script>alert(1)</script><img src=x onerror=y>')).toEqual([
      { text: '<script>alert(1)</script><img src=x onerror=y>', bold: false },
    ])
  })
  it('HTML 문자로 들어온 태그도 글자로만 보인다', () => {
    expect(naverParts('&lt;b&gt;굵게 아님&lt;/b&gt;')).toEqual([{ text: '<b>굵게 아님</b>', bold: false }])
  })
  it('빈 문자열은 빈 목록', () => {
    expect(naverParts('')).toEqual([])
  })
})

describe('decodeEntities', () => {
  it('자주 쓰는 이름과 숫자 문자', () => {
    expect(decodeEntities('&quot;HBM&quot; 확대 &amp; 투자 &#39;A&#x27;')).toBe('"HBM" 확대 & 투자 \'A\'')
  })
  it('모르는 이름·잘못된 숫자는 그대로', () => {
    expect(decodeEntities('&foo; &#0; AT&T')).toBe('&foo; &#0; AT&T')
  })
})
