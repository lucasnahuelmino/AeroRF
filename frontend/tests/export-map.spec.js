import { describe, expect, it, vi } from 'vitest'
import { mapExportFilename, renderMapPng } from '../src/map/exportMap.js'

describe('PNG map export', () => {
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
    vi.restoreAllMocks()
  })
})
