import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import LoginScreen from './components/LoginScreen.jsx'
import { getStoredAuthHeader, clearStoredAuthHeader } from './auth.js'

const REQUIRE_LOGIN = Boolean(import.meta.env.VITE_API_BASE_URL)

function Root() {
  const [authed, setAuthed] = useState(() => !REQUIRE_LOGIN || Boolean(getStoredAuthHeader()))
  if (REQUIRE_LOGIN && !authed) {
    return <LoginScreen onSuccess={() => setAuthed(true)} />
  }
  function handleLogout() {
    clearStoredAuthHeader()
    setAuthed(false)
  }
  return <App onLogout={REQUIRE_LOGIN ? handleLogout : undefined} />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
