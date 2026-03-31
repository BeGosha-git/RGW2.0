import React from 'react'

function normalizeName(name) {
  const raw = String(name || '').trim()
  if (!raw) return ''
  // allow mv_walk_1..mv_walk_6 -> mv_walk
  return raw.replace(/_\d+$/g, '')
}

function Svg({ children, size = 18 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

export default function IconGlyph({ name, size = 18, title = '' }) {
  const n = normalizeName(name)
  const common = {
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
  }

  if (!n) return null

  // Movement/gesture themed set. All icons inherit CSS `color` (set to white in UI).
  let node = null

  if (n === 'mv_walk') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <circle cx="9" cy="5" r="2" {...common} />
        <path d="M9 7v4l-2 3" {...common} />
        <path d="M9 11l3 2 2 4" {...common} />
        <path d="M8 21l2-6" {...common} />
        <path d="M14 21l-2-6" {...common} />
      </Svg>
    )
  } else if (n === 'mv_run') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <circle cx="10" cy="5" r="2" {...common} />
        <path d="M10 7l2 3 4 1" {...common} />
        <path d="M9 12l-3 3" {...common} />
        <path d="M12 10l-1 4 5 2" {...common} />
        <path d="M8 21l3-7" {...common} />
      </Svg>
    )
  } else if (n === 'mv_jump') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <circle cx="12" cy="5" r="2" {...common} />
        <path d="M8 12l4-3 4 3" {...common} />
        <path d="M9 21l3-7 3 7" {...common} />
        <path d="M3 12h4" {...common} />
        <path d="M17 12h4" {...common} />
      </Svg>
    )
  } else if (n === 'mv_squat') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <circle cx="12" cy="5" r="2" {...common} />
        <path d="M12 7v4" {...common} />
        <path d="M8 14h8" {...common} />
        <path d="M9 14l-2 4" {...common} />
        <path d="M15 14l2 4" {...common} />
        <path d="M7 21h10" {...common} />
      </Svg>
    )
  } else if (n === 'mv_sit') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <circle cx="10" cy="6" r="2" {...common} />
        <path d="M10 8v5l3 2" {...common} />
        <path d="M8 21l2-6" {...common} />
        <path d="M13 15h6" {...common} />
        <path d="M16 15v6" {...common} />
      </Svg>
    )
  } else if (n === 'mv_stand') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <circle cx="12" cy="5" r="2" {...common} />
        <path d="M12 7v6" {...common} />
        <path d="M9 21l3-8 3 8" {...common} />
        <path d="M7 11h10" {...common} />
      </Svg>
    )
  } else if (n === 'mv_wave') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <path d="M7 13c2-2 3-4 3-7" {...common} />
        <path d="M10 6c2 1 3 3 3 5" {...common} />
        <path d="M13 11c2 0 4 2 4 4" {...common} />
        <path d="M6 20c2 0 4-1 6-3" {...common} />
      </Svg>
    )
  } else if (n === 'mv_hug') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <circle cx="12" cy="7" r="2" {...common} />
        <path d="M6 14c2-2 4-3 6-3s4 1 6 3" {...common} />
        <path d="M7 14c1 4 3 6 5 6s4-2 5-6" {...common} />
        <path d="M9 15c1 1 2 2 3 2s2-1 3-2" {...common} />
      </Svg>
    )
  } else if (n === 'mv_dance') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <circle cx="12" cy="5" r="2" {...common} />
        <path d="M12 7l-2 4 3 2" {...common} />
        <path d="M10 11l-4 2" {...common} />
        <path d="M13 13l4 2" {...common} />
        <path d="M9 21l3-6 3 6" {...common} />
      </Svg>
    )
  } else if (n === 'mv_turn_left') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <path d="M10 7l-4 4 4 4" {...common} />
        <path d="M6 11h7a5 5 0 0 1 5 5v1" {...common} />
      </Svg>
    )
  } else if (n === 'mv_turn_right') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <path d="M14 7l4 4-4 4" {...common} />
        <path d="M18 11H11a5 5 0 0 0-5 5v1" {...common} />
      </Svg>
    )
  } else if (n === 'mv_stop') {
    node = (
      <Svg size={size}>
        {title ? <title>{title}</title> : null}
        <path d="M7 7h10v10H7z" {...common} />
      </Svg>
    )
  }

  // fallback: if it's not a known id, render raw text (legacy emoji)
  if (!node) {
    return (
      <span aria-hidden="true" title={title || String(name || '')} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        {String(name || '')}
      </span>
    )
  }

  return <span className="rgw2-icon-glyph">{node}</span>
}

