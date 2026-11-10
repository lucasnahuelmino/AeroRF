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

/**
 * Collect every drawable symbol inside the map's markers before the capture.
 *
 * html2canvas 1.4.1 composes the base map, the vectors and the DivIcon
 * backgrounds correctly, but it never paints the `<img>`/`<svg>` children of
 * the markers when the canvas is rendered with `scale > 1`: the export comes
 * back with blank discs. Instead of shipping an incomplete PNG, the symbols
 * are drawn by hand on top of the composed canvas.
 *
 * The positions are read from the live DOM right before html2canvas clones
 * it, so the measured rectangles match the capture (Leaflet's `translate3d`
 * is already included in `getBoundingClientRect`). Everything is same-origin,
 * so the canvas never gets tainted.
 *
 * @param {HTMLElement} container the map container being exported
 * @returns {Promise<Array<{element: Element, source: CanvasImageSource, angle: number, x: number, y: number, width: number, height: number}>>}
 */
async function collectMarkerSymbols(container) {
  const area = container.getBoundingClientRect()
  if (area.width === 0 || area.height === 0) return []

  const symbols = []
  const svgCache = new Map()

  for (const node of container.querySelectorAll('.leaflet-marker-icon, .leaflet-tooltip')) {
    if (node.closest('.leaflet-control')) continue
    const nodeRect = node.getBoundingClientRect()
    if (nodeRect.width === 0 || nodeRect.height === 0) continue

    const targets = []
    if (node.matches('img, svg')) targets.push(node)
    targets.push(...node.querySelectorAll('img, svg'))

    for (const element of targets) {
      const symbol = await prepareMarkerSymbol(element, node, area, svgCache)
      if (symbol) symbols.push(symbol)
    }
  }
  return symbols
}

async function prepareMarkerSymbol(element, node, area, svgCache) {
  const rect = element.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return null

  // Leaflet rotates the aircraft from the symbol itself (or a wrapper), so the
  // rotation is accumulated from the symbol up to the marker element.
  let angle = 0
  for (let current = element; current && current !== node; current = current.parentElement) {
    const matrix = getComputedStyle(current).transform
    if (!matrix || matrix === 'none') continue
    const values = matrix.match(/matrix\(([^)]+)\)/)
    if (!values) continue
    const [a, b] = values[1].split(',').map(Number)
    angle += Math.atan2(b, a)
  }

  let source = element
  let width = rect.width
  let height = rect.height

  if (element.tagName.toLowerCase() === 'svg') {
    // A live SVG node cannot be drawn onto another canvas: serialize it once
    // (without its own rotation, applied below through the context).
    const clone = element.cloneNode(true)
    clone.style.transform = 'none'
    const markup = new XMLSerializer().serializeToString(clone)
    let image = svgCache.get(markup)
    if (!image) {
      image = new Image()
      image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`
      if (typeof image.decode === 'function') await image.decode().catch(() => {})
      svgCache.set(markup, image)
    }
    source = image
    width = element.width?.baseVal?.value || rect.width
    height = element.height?.baseVal?.value || rect.height
  }

  if (angle !== 0) {
    // Under rotation the measured rectangle is the bounding box: use the
    // layout size and rotate around the centre instead.
    width = element.width || width
    height = element.height || height
  }

  return {
    element,
    source,
    angle,
    x: rect.left - area.left + rect.width / 2,
    y: rect.top - area.top + rect.height / 2,
    width,
    height,
  }
}

/**
 * Draw the prepared marker symbols on top of the html2canvas output.
 *
 * The canvas still carries html2canvas' own transform (scale + origin
 * translation), so the identity transform is restored first and every
 * coordinate is multiplied by `scale` by hand.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {Array} symbols
 * @param {number} scale
 */
function paintMarkerSymbols(canvas, symbols, scale) {
  if (!symbols.length) return
  const context = canvas.getContext('2d')
  if (!context) return

  for (const symbol of symbols) {
    if (symbol.element.isConnected === false) continue
    context.save()
    context.setTransform(1, 0, 0, 1, 0, 0)
    context.translate(symbol.x * scale, symbol.y * scale)
    if (symbol.angle !== 0) context.rotate(symbol.angle)
    try {
      context.drawImage(
        symbol.source,
        (-symbol.width * scale) / 2,
        (-symbol.height * scale) / 2,
        symbol.width * scale,
        symbol.height * scale,
      )
    } catch {
      // A broken symbol must not invalidate the rest of the export.
    }
    context.restore()
  }
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
    const symbols = await collectMarkerSymbols(container)
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
    paintMarkerSymbols(canvas, symbols, scale)

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
