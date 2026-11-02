import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

// 저장하지 않은 코멘트가 있을 때 이동을 막으려면(useBlocker) 데이터 라우터가 필요하다. 실제 경로는 App 안의 Routes가 정한다.
const router = createBrowserRouter([{ path: '*', element: <App /> }])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
