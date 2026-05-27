/**
 * OperationalActions — Bulk actions, toolbar, confirm modal, comments drawer.
 * Fase 3: Operational Action Layer
 */
import React, { useState } from 'react'

// ── Action Toolbar ───────────────────────────────────────────────────

interface ActionToolbarProps {
  selectedCount: number
  selectedIds: number[]
  onAction: (action: string, reason?: string, notes?: string, overrideReason?: string) => void
  onClear: () => void
}

export function ActionToolbar({ selectedCount, selectedIds, onAction, onClear }: ActionToolbarProps) {
  const [showModal, setShowModal] = useState(false)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [notes, setNotes] = useState('')
  const [overrideReason, setOverrideReason] = useState('')

  if (selectedCount === 0) return null

  const needsOverride = (action: string) => action === 'approve'

  const handleConfirm = () => {
    if (pendingAction) {
      onAction(pendingAction, reason || undefined, notes || undefined,
        needsOverride(pendingAction) ? (overrideReason || undefined) : undefined)
      setShowModal(false)
      setPendingAction(null)
      setReason('')
      setNotes('')
      setOverrideReason('')
    }
  }

  const openConfirm = (action: string) => {
    setPendingAction(action)
    setReason('')
    setNotes('')
    setOverrideReason('')
    setShowModal(true)
  }

  const actionLabel = (a: string) =>
    a === 'approve' ? 'Aprobar' : a === 'block' ? 'Bloquear' :
    a === 'manual_review' ? 'Revision' : a === 'mark_paid' ? 'Pagar' : a

  const actionColor = (a: string) =>
    a === 'approve' ? 'bg-green-600 hover:bg-green-700' :
    a === 'block' ? 'bg-red-600 hover:bg-red-700' :
    a === 'manual_review' ? 'bg-yellow-600 hover:bg-yellow-700' :
    a === 'mark_paid' ? 'bg-blue-600 hover:bg-blue-700' :
    'bg-gray-600'

  return (
    <>
      <div className="sticky bottom-0 z-30 bg-white border-t-2 border-blue-500 shadow-lg -mx-1 px-4 py-2.5 flex items-center gap-3">
        <span className="text-sm font-bold text-blue-700 whitespace-nowrap">
          {selectedCount} seleccionados
        </span>

        <div className="flex items-center gap-1.5 flex-1">
          {['approve', 'manual_review', 'block', 'mark_paid'].map(action => (
            <button
              key={action}
              onClick={() => openConfirm(action)}
              className={`px-3 py-1.5 text-xs font-medium text-white rounded transition-colors ${actionColor(action)}`}
            >
              {actionLabel(action)} ({selectedCount})
            </button>
          ))}
        </div>

        <button
          onClick={onClear}
          className="px-2 py-1 text-xs text-gray-400 hover:text-red-500 border border-gray-200 rounded"
        >
          Cancelar
        </button>
      </div>

      {/* Confirm Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-lg shadow-xl p-5 w-full max-w-md">
            <h3 className="text-sm font-semibold mb-3">
              {actionLabel(pendingAction || '')} {selectedCount} linea{selectedCount !== 1 ? 's' : ''}
            </h3>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Motivo</label>
                <input
                  type="text"
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                  className="w-full border rounded px-3 py-1.5 text-sm"
                  placeholder="Motivo de la operacion"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Comentario</label>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  className="w-full border rounded px-3 py-1.5 text-sm"
                  rows={2}
                  placeholder="Notas adicionales"
                />
              </div>

              {needsOverride(pendingAction || '') && (
                <div className="bg-amber-50 border border-amber-200 rounded p-3">
                  <label className="block text-xs font-medium text-amber-800 mb-1">
                    Override requerido para lineas criticas
                  </label>
                  <input
                    type="text"
                    value={overrideReason}
                    onChange={e => setOverrideReason(e.target.value)}
                    className="w-full border border-amber-300 rounded px-3 py-1.5 text-sm"
                    placeholder="Razon del override (obligatorio para aprobar criticos)"
                  />
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 mt-4 justify-end">
              <button
                onClick={() => setShowModal(false)}
                className="px-3 py-1.5 text-xs border border-gray-200 rounded hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                onClick={handleConfirm}
                className={`px-4 py-1.5 text-xs font-medium text-white rounded ${actionColor(pendingAction || '')}`}
              >
                Confirmar {actionLabel(pendingAction || '')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ── Select All Checkbox ──────────────────────────────────────────────

export function SelectAllCheckbox({
  checked, onChange, total, selectedCount
}: {
  checked: boolean; onChange: () => void; total: number; selectedCount: number
}) {
  return (
    <label className="flex items-center gap-1 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
      />
      {selectedCount > 0 && selectedCount < total && (
        <span className="text-[10px] text-gray-400">({selectedCount})</span>
      )}
    </label>
  )
}

// ── Row Checkbox ─────────────────────────────────────────────────────

export function RowCheckbox({
  checked, onChange
}: {
  checked: boolean; onChange: () => void
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={onChange}
      className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
      onClick={e => e.stopPropagation()}
    />
  )
}

// ── Keyboard shortcuts hook ──────────────────────────────────────────

export function useOperationalShortcuts(handlers: {
  onApproveAll?: () => void
  onReviewAll?: () => void
  onBlockAll?: () => void
  onClear?: () => void
}) {
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.ctrlKey || e.metaKey) {
        if (e.key === 'a' || e.key === 'A') { e.preventDefault(); handlers.onApproveAll?.() }
        if (e.key === 'r' || e.key === 'R') { e.preventDefault(); handlers.onReviewAll?.() }
        if (e.key === 'b' || e.key === 'B') { e.preventDefault(); handlers.onBlockAll?.() }
      }
      if (e.key === 'Escape') { handlers.onClear?.() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [handlers])
}

// ── Exports for use in components ────────────────────────────────────

export { executeLineAction, executeBulkAction }
