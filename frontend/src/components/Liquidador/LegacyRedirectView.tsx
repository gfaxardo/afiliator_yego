import { useNavigate } from 'react-router-dom'

interface Props {
  name: string
}

export default function LegacyRedirectView({ name }: Props) {
  const navigate = useNavigate()

  return (
    <div className="max-w-2xl mx-auto mt-20">
      <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-8 text-center">
        <div className="text-3xl mb-4">&#9888;</div>
        <h2 className="text-lg font-semibold text-yellow-800 mb-2">
          Flujo legacy oculto
        </h2>
        <p className="text-sm text-yellow-700 mb-4">
          <strong>{name}</strong> ya no esta disponible como ruta principal de carga.
          Usa <strong>Carga Unificada</strong> para subir datos.
        </p>
        <p className="text-xs text-yellow-600 mb-6">
          Este flujo queda solo para contingencia tecnica.
          Puede reactivarse con <code className="bg-yellow-100 px-1 rounded">VITE_ENABLE_LEGACY_IMPORTS=true</code>
        </p>
        <button
          onClick={() => navigate('/scout-liq/unified-load')}
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm font-medium"
        >
          Ir a Carga Unificada
        </button>
      </div>
    </div>
  )
}
