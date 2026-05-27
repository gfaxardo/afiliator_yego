/**
 * ErrorBoundary — Global error fallback for the entire app.
 * Prevents "white screen of death" on uncaught render errors.
 */
import React from 'react'

interface Props {
  children: React.ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 p-8">
          <div className="max-w-md bg-white border border-red-200 rounded-lg shadow-sm p-6 text-center">
            <div className="text-3xl mb-3">⚠</div>
            <h2 className="text-base font-semibold text-gray-800 mb-2">Error inesperado</h2>
            <p className="text-xs text-gray-500 mb-4">
              Ocurrio un error al renderizar esta pantalla. Intenta refrescar la pagina.
            </p>
            <p className="text-[10px] text-red-500 font-mono mb-4 bg-red-50 p-2 rounded truncate">
              {this.state.error?.message}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.reload()
              }}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
            >
              Refrescar pagina
            </button>
            <button
              onClick={() => window.history.back()}
              className="px-4 py-2 ml-2 border border-gray-200 text-gray-600 text-sm rounded hover:bg-gray-50 transition-colors"
            >
              Volver atras
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
