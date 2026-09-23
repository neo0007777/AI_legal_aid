import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { LocalModeProvider } from './context/LocalModeContext'
import { PersonaProvider } from './context/PersonaContext'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <LocalModeProvider>
          <PersonaProvider>
            <App />
          </PersonaProvider>
        </LocalModeProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
