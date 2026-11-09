import { useState } from 'react'
import styles from '../app.module.css'

function iconUrl(homepage: string | null | undefined): string | null {
  if (!homepage) return null
  try {
    const url = new URL(homepage)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    url.pathname = '/favicon.ico'
    url.search = ''
    url.hash = ''
    return url.toString()
  } catch {
    return null
  }
}

export function CompanyLogo({ name, homepage }: { name: string; homepage?: string | null }) {
  const [failed, setFailed] = useState(false)
  const src = iconUrl(homepage)
  return (
    <span className={styles.companyLogo} aria-hidden="true">
      {src && !failed
        ? <img src={src} alt="" onError={() => setFailed(true)} />
        : <span>{Array.from(name).slice(0, 2).join('')}</span>}
    </span>
  )
}
