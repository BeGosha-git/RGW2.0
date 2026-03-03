import React, { Suspense, lazy } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import { NAV_ICONS } from './constants/icons'
import Loading from './components/Loading'
import './App.css'

// Lazy loading для всех страниц
const HomePage = lazy(() => import('./pages/HomePage'))
const FileEditorPage = lazy(() => import('./pages/FileEditorPage'))
const RobotControlPage = lazy(() => import('./pages/RobotControlPage'))
const RobotsPage = lazy(() => import('./pages/RobotsPage'))
const TerminalPage = lazy(() => import('./pages/TerminalPage'))
const ServicesPage = lazy(() => import('./pages/ServicesPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const MotorControlPage = lazy(() => import('./pages/MotorControlPage'))

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
    <nav className="main-nav">
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
  )
}

function App() {
  return (
    <Router>
      <div className="app">
        <Navigation />
        <main className="main-content">
          <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/editor" element={<FileEditorPage />} />
            <Route path="/robots" element={<RobotsPage />} />
            <Route path="/robots-old" element={<RobotControlPage />} />
            <Route path="/services" element={<ServicesPage />} />
              <Route path="/motors" element={<MotorControlPage />} />
            <Route path="/terminal" element={<TerminalPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
          </Suspense>
        </main>
      </div>
    </Router>
  )
}

export default App
