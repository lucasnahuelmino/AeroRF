/**
 * tests/setup.js
 * ─────────────
 * jsdom shims for component tests.
 *
 * jsdom implements enough DOM for Vue, but not for a few browser APIs that
 * Leaflet and ResizeObserver touch. Stubbing them here keeps every test
 * file free of setup noise.
 */

import { vi } from 'vitest'

// ─── ResizeObserver ─────────────────────────────────────────────────────────
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// ─── matchMedia ─────────────────────────────────────────────────────────────
window.matchMedia =
  window.matchMedia ||
  ((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }))

// ─── Canvas (Leaflet measures text with it) ────────────────────────────────
// MapEngine sets `preferCanvas: true` on purpose — hundreds of vector
// layers stay smooth. That means Leaflet asks for a 2D context, and
// jsdom's `getContext` throws "Not implemented" rather than returning
// null. Stubbing it is a test-environment concern; the production choice
// of canvas over SVG is not changed to suit the tests.
if (!HTMLCanvasElement.prototype.getContext.__aerorfStub) {
  const context2d = {
    canvas: null,
    fillStyle: '#000',
    strokeStyle: '#000',
    lineWidth: 1,
    lineCap: 'butt',
    lineJoin: 'miter',
    globalAlpha: 1,
    globalCompositeOperation: 'source-over',
    font: '12px sans-serif',
    textAlign: 'start',
    textBaseline: 'alphabetic',
    shadowBlur: 0,
    shadowColor: 'rgba(0,0,0,0)',
    lineDashOffset: 0,
    save() {},
    restore() {},
    scale() {},
    rotate() {},
    translate() {},
    transform() {},
    setTransform() {},
    resetTransform() {},
    clearRect() {},
    fillRect() {},
    strokeRect() {},
    beginPath() {},
    closePath() {},
    moveTo() {},
    lineTo() {},
    bezierCurveTo() {},
    quadraticCurveTo() {},
    arc() {},
    arcTo() {},
    ellipse() {},
    rect() {},
    fill() {},
    stroke() {},
    clip() {},
    isPointInPath: () => false,
    setLineDash() {},
    getLineDash: () => [],
    drawImage() {},
    createLinearGradient: () => ({ addColorStop() {} }),
    createRadialGradient: () => ({ addColorStop() {} }),
    createPattern: () => null,
    measureText: (text) => ({
      width: String(text ?? '').length * 6,
      actualBoundingBoxAscent: 8,
      actualBoundingBoxDescent: 2,
    }),
    fillText() {},
    strokeText() {},
  }

  const stub = function getContext(type) {
    if (type !== '2d') return null
    if (!this.__ctx2d) {
      this.__ctx2d = Object.create(context2d)
      this.__ctx2d.canvas = this
    }
    return this.__ctx2d
  }
  stub.__aerorfStub = true
  HTMLCanvasElement.prototype.getContext = stub
}

// ─── Element sizes: jsdom reports 0, which breaks Leaflet's fitBounds ─────
Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
  configurable: true,
  get() {
    return 1024
  },
})
Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
  configurable: true,
  get() {
    return 768
  },
})
Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
  configurable: true,
  get() {
    return 1024
  },
})
Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
  configurable: true,
  get() {
    return 768
  },
})

// ─── Scrolling APIs Leaflet binds ───────────────────────────────────────────
Element.prototype.scrollIntoView = vi.fn()
window.scrollTo = vi.fn()

// ─── Pointer events used by Leaflet drag ────────────────────────────────────
if (!window.PointerEvent) {
  window.PointerEvent = window.MouseEvent
}

// ─── localStorage is present in jsdom, but keep it isolated per test ───────
beforeEach(() => {
  window.localStorage.clear()
})
