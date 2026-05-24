/**
 * Acquisition Anchor Badges — Fase 2A.3
 * Badges operacionales consistentes para el liquidador.
 *
 * Usar como: <AcquisitionBadge type="NEW" />
 * O: <AcquisitionBadge type="REACTIVATED" label="Reactivado" />
 */
import React from 'react'

const BADGE_STYLES: Record<string, string> = {
  // Green — healthy/official
  NEW:            'bg-green-100 text-green-800 border-green-300',
  PAYABLE:        'bg-green-100 text-green-800 border-green-300',
  STRONG:         'bg-green-50 text-green-700 border-green-200',

  // Yellow — needs attention
  FALLBACK:       'bg-yellow-100 text-yellow-800 border-yellow-300',
  MANUAL_REVIEW:  'bg-yellow-100 text-yellow-800 border-yellow-300',
  MEDIUM:         'bg-yellow-50 text-yellow-700 border-yellow-200',

  // Orange — warning
  REACTIVATED:    'bg-orange-100 text-orange-800 border-orange-300',
  APPROX:         'bg-orange-100 text-orange-800 border-orange-300',

  // Red — blocked/danger
  BLOCKED:        'bg-red-100 text-red-800 border-red-300',
  WEAK:           'bg-red-50 text-red-700 border-red-200',

  // Blue/Gray — informational
  FLEET:          'bg-blue-100 text-blue-800 border-blue-300',
  LEGACY:         'bg-gray-100 text-gray-600 border-gray-300',
}

const DEFAULT_LABELS: Record<string, string> = {
  NEW: 'NEW',
  REACTIVATED: 'REACT',
  FLEET: 'FLEET',
  FALLBACK: 'FALLBACK',
  APPROX: 'APROX',
  PAYABLE: 'PAGABLE',
  MANUAL_REVIEW: 'REVISAR',
  BLOCKED: 'BLOQ',
  LEGACY: 'LEGACY',
  STRONG: 'STRONG',
  MEDIUM: 'MEDIUM',
  WEAK: 'DEBIL',
}

interface Props {
  type: string
  label?: string
  className?: string
}

export function AcquisitionBadge({ type, label, className = '' }: Props) {
  const style = BADGE_STYLES[type] || BADGE_STYLES.FALLBACK
  const text = label || DEFAULT_LABELS[type] || type
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${style} ${className}`}>
      {text}
    </span>
  )
}

/**
 * Renders all applicable anchor badges for a driver line.
 */
export function AnchorBadgeStack({
  acquisitionType,
  reactivationFlag,
  anchorConfidence,
  isAutoPayable,
  paymentAnchorStatus,
  dateBasis,
  daysHireVsAnchor,
}: {
  acquisitionType?: string | null
  reactivationFlag?: boolean
  anchorConfidence?: string | null
  isAutoPayable?: boolean
  paymentAnchorStatus?: string | null
  dateBasis?: string | null
  daysHireVsAnchor?: number | null
}) {
  const badges: React.ReactNode[] = []

  // Fleet
  if (acquisitionType === 'fleet_migration') {
    badges.push(<AcquisitionBadge key="fleet" type="FLEET" />)
  } else {
    // Reactivated vs New
    if (reactivationFlag) {
      badges.push(<AcquisitionBadge key="react" type="REACTIVATED" />)
    } else if (acquisitionType && acquisitionType.includes('new')) {
      badges.push(<AcquisitionBadge key="new" type="NEW" />)
    }
  }

  // Payment status
  if (paymentAnchorStatus === 'blocked_missing_official_anchor') {
    badges.push(<AcquisitionBadge key="blocked" type="BLOCKED" label="BLOQ ANCLA" />)
  } else if (paymentAnchorStatus === 'reported_pending_validation' ||
             paymentAnchorStatus?.includes('manual_review')) {
    badges.push(<AcquisitionBadge key="review" type="MANUAL_REVIEW" />)
  } else if (isAutoPayable) {
    badges.push(<AcquisitionBadge key="pay" type="PAYABLE" />)
  }

  // Confidence
  if (anchorConfidence === 'weak') {
    badges.push(<AcquisitionBadge key="weak" type="WEAK" />)
  } else if (anchorConfidence === 'medium' && !acquisitionType?.includes('fleet')) {
    badges.push(<AcquisitionBadge key="fallback" type="FALLBACK" />)
  }

  // Legacy
  if (dateBasis === 'hire_date_legacy') {
    badges.push(<AcquisitionBadge key="legacy" type="LEGACY" />)
  }

  // High gap warning
  if (daysHireVsAnchor && Math.abs(daysHireVsAnchor) > 30) {
    badges.push(<span key="gap" className="px-1.5 py-0.5 rounded text-[10px] font-medium border bg-amber-100 text-amber-700 border-amber-300"
      title={`Diferencia anchor vs hire: ${daysHireVsAnchor}d`}>
      GAP
    </span>)
  }

  return <div className="flex items-center gap-1 flex-wrap">{badges}</div>
}
