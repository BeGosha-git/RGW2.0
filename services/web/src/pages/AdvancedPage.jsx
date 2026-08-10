import React from 'react'
import WebRTCVideo from '../components/WebRTCVideo'
import './AdvancedPage.css'

export default function AdvancedPage() {
  return (
    <div className="advanced-page">
      <div className="advanced-video">
        <WebRTCVideo
          signalingUrl="/api/cameras/advanced/webrtc/offer"
          label="advanced"
          qualityMode="high"
        />
      </div>
    </div>
  )
}

