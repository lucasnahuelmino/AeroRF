import { afterEach, describe, expect, it, vi } from 'vitest'
import { mapExportFilename, renderMapPng } from '../src/map/exportMap.js'

vi.mock('html2canvas', () => ({ default: vi.fn() }))

describe('PNG map export', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('creates a timestamped AeroRF PNG filename', () => {
    expect(mapExportFilename(new Date(2026, 0, 2, 3, 4, 5)))
      .toBe('AeroRF_Mapa_2026-01-02_03-04-05.png')
  })

  it('rejects a missing map container explicitly', async () => {
    await expect(renderMapPng(null)).rejects.toThrow('No se encontró el área cartográfica')
  })

  it('rejects blocked tile CORS instead of delivering an incomplete image', async () => {
    const container = document.createElement('div')
    const tile = document.createElement('img')
    tile.className = 'leaflet-tile'
    Object.defineProperties(tile, {
      complete: { value: true },
      naturalWidth: { value: 256 },
    })
    container.append(tile)

    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      clearRect: vi.fn(),
      drawImage: vi.fn(),
      getImageData: () => { throw new DOMException('tainted canvas', 'SecurityError') },
    })

    await expect(renderMapPng(container)).rejects.toThrow('bloqueó la composición de imágenes por CORS')
  })

  it('repaints marker symbols on top of the composed canvas', async () => {
    const drawImage = vi.fn()
    const context = {
      setTransform: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      translate: vi.fn(),
      rotate: vi.fn(),
      drawImage,
    }
    const fakeCanvas = {
      width: 800,
      height: 600,
      getContext: () => context,
      toBlob: (callback) => callback(new Blob(['png'], { type: 'image/png' })),
    }
    const html2canvas = (await import('html2canvas')).default
    html2canvas.mockResolvedValue(fakeCanvas)

    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      clearRect: vi.fn(),
      drawImage: vi.fn(),
      getImageData: () => ({ data: new Uint8ClampedArray(4) }),
    })

    const container = document.createElement('div')
    const tile = document.createElement('img')
    tile.className = 'leaflet-tile'
    Object.defineProperties(tile, {
      complete: { value: true },
      naturalWidth: { value: 256 },
    })
    const marker = document.createElement('div')
    marker.className = 'leaflet-marker-icon'
    const icon = document.createElement('img')
    icon.src = '/iconos/aeropuerto.svg'
    marker.append(icon)
    container.append(tile, marker)
    document.body.append(container)

    container.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 400, height: 300, right: 400, bottom: 300 })
    marker.getBoundingClientRect = () =>
      ({ left: 100, top: 80, width: 26, height: 26, right: 126, bottom: 106 })
    icon.getBoundingClientRect = () =>
      ({ left: 104, top: 84, width: 18, height: 18, right: 122, bottom: 102 })

    const blob = await renderMapPng(container, { scale: 2 })

    expect(blob.size).toBeGreaterThan(0)
    // Centre of the icon (104 + 9, 84 + 9) multiplied by the export scale.
    expect(context.translate).toHaveBeenCalledWith(226, 186)
    expect(drawImage).toHaveBeenCalledTimes(1)
    expect(drawImage).toHaveBeenCalledWith(icon, -18, -18, 36, 36)
    expect(context.rotate).not.toHaveBeenCalled()

    html2canvas.mockReset()
  })
})
