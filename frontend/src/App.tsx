import { Link, Route, Routes } from 'react-router-dom'
import styles from './app.module.css'
import Home from './pages/Home'
import Progress from './pages/Progress'
import ReportList from './pages/ReportList'
import ReportView from './pages/ReportView'
import UploadReports from './pages/UploadReports'

export default function App() {
  return (
    <>
      <header className={styles.topbar}>
        <Link to="/" className={styles.brand}>기업분석 리포트</Link>
        <nav>
          <Link to="/">홈</Link>
          <Link to="/reports">리포트 목록</Link>
        </nav>
      </header>
      <main className={styles.main}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/upload-reports" element={<UploadReports />} />
          <Route path="/jobs/:jobId" element={<Progress />} />
          <Route path="/reports" element={<ReportList />} />
          <Route path="/reports/:reportId" element={<ReportView />} />
          <Route path="*" element={<p>없는 주소입니다. <Link to="/">홈으로</Link></p>} />
        </Routes>
      </main>
    </>
  )
}
