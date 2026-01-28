import React, { useState, useEffect } from 'react'
import Card from '../components/Card'
import Button from '../components/Button'
import SelectBox from '../components/SelectBox'
import Loading from '../components/Loading'
import { ICONS } from '../constants/icons'
import { settingsApi } from '../utils/api'
import { useToast } from '../hooks/useToast'
import Toast from '../components/Toast'
import './SettingsPage.css'

function SettingsPage() {
  const [settings, setSettings] = useState({
    RobotType: '',
    RobotID: '',
    RobotGroup: '',
    VersionPriority: ''
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast, showToast, hideToast } = useToast()

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      setLoading(true)
      const result = await settingsApi.get()
      if (result.success && result.settings) {
        setSettings(result.settings)
      } else {
        showToast('Ошибка загрузки настроек', 'error')
      }
    } catch (error) {
      showToast(`Ошибка загрузки настроек: ${error.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const saveSettings = async () => {
    try {
      setSaving(true)
      const result = await settingsApi.update(settings)
      if (result.success) {
        showToast('Настройки успешно сохранены', 'success')
      } else {
        showToast(`Ошибка сохранения: ${result.message || 'Неизвестная ошибка'}`, 'error')
      }
    } catch (error) {
      showToast(`Ошибка сохранения: ${error.message}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  if (loading) {
    return (
      <div className="settings-page">
        <div className="settings-header">
          <h1>Настройки</h1>
        </div>
        <div className="settings-loading">
          <Loading text="Загрузка настроек..." />
        </div>
      </div>
    )
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>Настройки</h1>
      </div>

      <div className="settings-content">
        <Card title="Настройки робота" icon={ICONS.STATUS}>
          <div className="setting-item">
            <label className="setting-label">Тип робота:</label>
            <input
              type="text"
              className="setting-input"
              value={settings.RobotType || ''}
              onChange={(e) => updateSetting('RobotType', e.target.value)}
              placeholder="PC"
            />
          </div>

          <div className="setting-item">
            <label className="setting-label">ID робота:</label>
            <input
              type="text"
              className="setting-input"
              value={settings.RobotID || ''}
              onChange={(e) => updateSetting('RobotID', e.target.value)}
              placeholder="0001"
            />
          </div>

          <div className="setting-item">
            <label className="setting-label">Группа робота:</label>
            <input
              type="text"
              className="setting-input"
              value={settings.RobotGroup || ''}
              onChange={(e) => updateSetting('RobotGroup', e.target.value)}
              placeholder="green"
            />
          </div>

          <div className="setting-item">
            <label className="setting-label">Приоритет версии:</label>
            <SelectBox
              value={settings.VersionPriority || ''}
              onChange={(value) => updateSetting('VersionPriority', value)}
              options={[
                { value: 'STABLE', label: 'STABLE' },
                { value: 'BETA', label: 'BETA' },
                { value: 'ALPHA', label: 'ALPHA' }
              ]}
              placeholder="Выберите..."
              className="setting-select"
            />
          </div>
        </Card>

        <div className="settings-actions">
          <Button 
            onClick={saveSettings} 
            variant="primary"
            disabled={saving}
            loading={saving}
          >
            Сохранить настройки
          </Button>
          <Button 
            onClick={loadSettings} 
            variant="secondary"
            disabled={loading || saving}
          >
            Обновить
          </Button>
        </div>
      </div>

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          duration={toast.duration}
          onClose={hideToast}
        />
      )}
    </div>
  )
}

export default SettingsPage
