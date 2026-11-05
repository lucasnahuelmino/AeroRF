function assertReadableTiles(container) {
  const tiles = [...container.querySelectorAll('img.leaflet-tile')]
    .filter((tile) => tile.complete || tile.getBoundingClientRect().width > 0)
  if (!tiles.length) {
    throw new Error('No hay mosaicos cartográficos cargados para exportar.')
  }

  const probe = document.createElement('canvas')
  probe.width = 1
  probe.height = 1
  const context = probe.getContext('2d')
  if (!context) throw new Error('El navegador no pudo preparar el lienzo PNG.')

  for (const tile of tiles) {
    if (!tile.complete || tile.naturalWidth === 0) {
      throw new Error('Hay mosaicos incompletos. Espere a que termine de cargar el mapa y vuelva a intentar.')
    }
    try {
      context.clearRect(0, 0, 1, 1)
      context.drawImage(tile, 0, 0, 1, 1)
      context.getImageData(0, 0, 1, 1)
    } catch (error) {
      throw new Error(
        'El servidor de mapas bloqueó la composición de imágenes por CORS. No se descargó un PNG incompleto.',
        { cause: error },
      )
    }
  }
}

function nextPaint() {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
}

export async function renderMapPng(container, { engine, scale = 2 } = {}) {
  if (!(container instanceof HTMLElement)) {
    throw new Error('No se encontró el área cartográfica para exportar.')
  }
  assertReadableTiles(container)

  const drafts = [...(engine?._draftLayers?.values?.() || [])]
    .filter((layer) => engine.map?.hasLayer(layer))
  drafts.forEach((layer) => engine.map.removeLayer(layer))

  try {
    await nextPaint()
    const { default: html2canvas } = await import('html2canvas')
    const canvas = await html2canvas(container, {
      allowTaint: false,
      backgroundColor: '#0B1420',
      imageTimeout: 10000,
      logging: false,
      scale,
      useCORS: true,
      ignoreElements: (element) => element.closest?.('.leaflet-control-zoom') !== null,
    })
    if (canvas.width === 0 || canvas.height === 0) {
      throw new Error('La imagen cartográfica resultó vacía.')
    }

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
    if (!blob || blob.size === 0) throw new Error('No se pudo generar el archivo PNG.')
    return blob
  } finally {
    drafts.forEach((layer) => {
      if (!engine.map.hasLayer(layer)) layer.addTo(engine.map)
    })
  }
}

export function mapExportFilename(date = new Date()) {
  const pad = (value) => String(value).padStart(2, '0')
  return `AeroRF_Mapa_${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}_${pad(date.getHours())}-${pad(date.getMinutes())}-${pad(date.getSeconds())}.png`
}
