/**
 * RetryButton — Reintentar accion con feedback visual.
 */
import React, { useState } from 'react'

interface Props {
  onRetry: () => Promise<void> | void
  label?: string
  className?: string
}

export function RetryButton({ onRetry, label = 'Reintentar', className = '' }: Props) {
  const [trying, setTrying] = useState(false)

  const handle = async () => {
    setTrying(true)
    try {
      await onRetry()
    } finally {
      setTrying(false)
    }
  }

  return (
    <button
      onClick={handle}
      disabled={trying}
      className={`px-3 py-1 text-xs border border-amber-200 bg-amber-50 text-amber-700 rounded hover:bg-amber-100 disabled:opacity-50 transition-colors ${className}`}
    >
      {trying ? 'Reintentando...' : label}
    </button>
  )
}
