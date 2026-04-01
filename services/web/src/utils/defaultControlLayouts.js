function mkBtn({ id, commandId, label, icon, x, y, shape = 'circle', color = '#2196f3' }) {
  return {
    id,
    commandId,
    label,
    icon,
    shape,
    color,
    x: Number(x.toFixed(5)),
    y: Number(y.toFixed(5)),
    size: 64,
    targetIps: ['LOCAL'],
    program: [
      {
        type: 'command',
        id: `step-${id}`,
        commandId,
        delayBeforeMs: 0,
        delayAfterMs: 0,
        actionDurationMs: 0,
        targetIps: ['LOCAL'],
        waitContinue: false,
        useGo: false,
      },
    ],
  }
}

function edgePositions(n) {
  if (n <= 0) return []
  const top = Math.max(1, Math.floor(n / 4))
  const right = Math.max(1, Math.floor(n / 4))
  const bottom = Math.max(1, Math.floor(n / 4))
  const left = Math.max(1, n - top - right - bottom)

  const lin = (a, b, k, m) => (m <= 1 ? (a + b) / 2 : a + (b - a) * (k / (m - 1)))
  const pts = []

  for (let i = 0; i < top; i++) pts.push([lin(0.15, 0.85, i, top), 0.12])
  for (let i = 0; i < right; i++) pts.push([0.88, lin(0.18, 0.82, i, right)])
  for (let i = 0; i < bottom; i++) pts.push([lin(0.85, 0.15, i, bottom), 0.88])
  for (let i = 0; i < left; i++) pts.push([0.12, lin(0.82, 0.18, i, left)])

  return pts.slice(0, n)
}

export function buildDefaultControlLayouts() {
  const movements = [
    { commandId: 'g1_hug', label: 'HUG', icon: 'mv_hug_1' },
    { commandId: 'g1_high_wave', label: 'WAVE', icon: 'mv_wave_1' },
    { commandId: 'g1_face_wave', label: 'FACE', icon: 'mv_wave_2' },
    { commandId: 'g1_shake_hand', label: 'SHAKE', icon: 'mv_wave_3' },
    { commandId: 'g1_high_five', label: 'FIVE', icon: 'mv_wave_4' },
    { commandId: 'g1_clap', label: 'CLAP', icon: 'mv_dance_1' },
    { commandId: 'g1_heart', label: 'HEART', icon: 'mv_hug_2' },
    { commandId: 'g1_right_heart', label: 'R-HEART', icon: 'mv_hug_3' },
    { commandId: 'g1_hands_up', label: 'HANDS', icon: 'mv_jump_1' },
    { commandId: 'g1_reject', label: 'REJECT', icon: 'mv_stop_1' },
    { commandId: 'g1_left_kiss', label: 'L-KISS', icon: 'mv_hug_4' },
    { commandId: 'g1_right_kiss', label: 'R-KISS', icon: 'mv_hug_5' },
  ]

  const modes = [
    { commandId: 'g1_loco_start', label: 'START', icon: 'mv_run_1' },
    { commandId: 'g1_loco_damp', label: 'DAMP', icon: 'mv_stop_1' },
    { commandId: 'g1_loco_zero_torque', label: '0TORQ', icon: 'mv_stop_2' },
    { commandId: 'g1_loco_sit', label: 'SIT', icon: 'mv_sit_1' },
    { commandId: 'g1_loco_lie_to_stand', label: 'L→S', icon: 'mv_stand_1' },
    { commandId: 'g1_loco_squat_to_stand', label: 'SQ→ST', icon: 'mv_stand_2' },
    { commandId: 'g1_loco_high_stand', label: 'HIGH', icon: 'mv_stand_3' },
    { commandId: 'g1_loco_low_stand', label: 'LOW', icon: 'mv_squat_1' },
    { commandId: 'g1_loco_stop_move', label: 'STOP', icon: 'mv_stop_3' },
  ]

  const movePts = edgePositions(movements.length)
  const modePts = edgePositions(modes.length)

  const movementButtons = movements.map((b, i) =>
    mkBtn({
      id: `base-move-${b.commandId}`,
      commandId: b.commandId,
      label: b.label,
      icon: b.icon,
      x: movePts[i][0],
      y: movePts[i][1],
      shape: 'circle',
      color: '#2196f3',
    }),
  )

  const modeButtons = modes.map((b, i) =>
    mkBtn({
      id: `base-mode-${b.commandId}`,
      commandId: b.commandId,
      label: b.label,
      icon: b.icon,
      x: modePts[i][0],
      y: modePts[i][1],
      shape: 'square',
      color: '#9c27b0',
    }),
  )

  return {
    version: '1.0.0',
    layouts: [
      { id: 'layout-movements', name: 'Движения', buttons: movementButtons },
      { id: 'layout-modes', name: 'Режимы', buttons: modeButtons },
    ],
  }
}

