import React, { Suspense, lazy } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import { NAV_ICONS } from './constants/icons'
import Loading from './components/Loading'
import './App.css'

// Lazy loading для всех страниц
const HomePage = lazy(() => import('./pages/HomePage'))
const FileEditorPage = lazy(() => import('./pages/FileEditorPage'))
const RobotsPage = lazy(() => import('./pages/RobotsPage'))
const TerminalPage = lazy(() => import('./pages/TerminalPage'))
const ServicesPage = lazy(() => import('./pages/ServicesPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const MotorControlPage = lazy(() => import('./pages/MotorControlPage'))
const ControlPage = lazy(() => import('./pages/ControlPage'))
const EditControlLayoutPage = lazy(() => import('./pages/EditControlLayoutPage'))

function Navigation() {
  const location = useLocation()

  const isActive = (path) => location.pathname === path

  const navItems = [
    { path: '/', label: 'Статус', icon: NAV_ICONS.HOME },
    { path: '/editor', label: 'Редактор', icon: NAV_ICONS.EDITOR },
    { path: '/robots', label: 'Роботы', icon: NAV_ICONS.ROBOTS },
    { path: '/services', label: 'Сервисы', icon: NAV_ICONS.SERVICES },
    { path: '/motors', label: 'Моторы', icon: '◉' },
    { path: '/terminal', label: 'Терминал', icon: NAV_ICONS.TERMINAL },
    { path: '/settings', label: 'Настройки', icon: '⚙' }
  ]

  return (
    <>
      {/* Desktop top navigation */}
      <nav className="main-nav desktop-nav">
        <div className="nav-container">
          <div className="nav-logo">
            <span className="glow-text">RGW</span>
            <span className="nav-version">2.0</span>
          </div>
          <div className="nav-links">
            {navItems.map(item => (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link ${isActive(item.path) ? 'active' : ''}`}
              >
                <span className="nav-link-icon">{item.icon}</span>
                {item.label}
              </Link>
            ))}
          </div>
        </div>
      </nav>

      {/* Mobile bottom navigation */}
      <nav className="mobile-bottom-nav">
        {navItems.map(item => (
          <Link
            key={item.path}
            to={item.path}
            className={`mobile-nav-item ${isActive(item.path) ? 'active' : ''}`}
          >
            <span className="mobile-nav-icon">{item.icon}</span>
            <span className="mobile-nav-label">{item.label}</span>
          </Link>
        ))}
      </nav>
    </>
  )
}

function App() {
  const FullscreenRoutes = () => {
    const location = useLocation()
    const hideNavigation = location.pathname === '/control' || location.pathname === '/editctl'

    return (
      <div className="app">
        {!hideNavigation && <Navigation />}
        <main className={`main-content ${hideNavigation ? 'main-content-fullscreen' : ''}`}>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/editor" element={<FileEditorPage />} />
              <Route path="/robots" element={<RobotsPage />} />
              <Route path="/services" element={<ServicesPage />} />
              <Route path="/motors" element={<MotorControlPage />} />
              <Route path="/terminal" element={<TerminalPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/control" element={<ControlPage />} />
              <Route path="/editctl" element={<EditControlLayoutPage />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    )
  }

  return (
    <Router>
      <FullscreenRoutes />
    </Router>
  )
}

export default App
