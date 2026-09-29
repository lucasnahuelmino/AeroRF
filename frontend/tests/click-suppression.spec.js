import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { MapEngine } from '@/map/MapEngine'
import { ToolManager, TOOLS } from '@/map/draw'

/**
 * The click-suppression flag, and who is responsible for it.
 *
 * `suppressClicks(value = true)` defaults to *on*, and the map's click handler
 * drops every click while it is set. Only `ToolManager.activate` ever turns it
 * off, and nothing turns it back on.
 *
 * That leaves the select tool depending on a flag it never sets: if no drawing
 * tool has been picked since the page loaded, the flag is still `true` and the
 * map publishes nothing — so clicking empty ground cannot clear the selection.
 */
let container
let engine

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-sup'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-sup' })
  engine.init()
  engine.setView(-34.6, -58.4, 11)
})

afterEach(() => {
  engine?.destroy()
  container?.remove()
})

const CLICK = { latlng: { lat: -34.6, lng: -58.4 } }

function countMapClicks() {
  const seen = []
  engine.on('click', (p) => seen.push(p))
  engine.map.fire('click', CLICK)
  return seen.length
}

describe('the click-suppression flag', () => {
  it('publishes map clicks on a fresh engine', () => {
    // The handler opens with `if (this._clickSuppressed) return`, so the flag
    // decides everything below. It is not initialised — `undefined`, which is
    // falsy — so a fresh engine publishes. Asserted as falsy rather than
    // `false`, because that is the actual value and the distinction is what
    // makes the suppression below work.
    expect(Boolean(engine._clickSuppressed), 'el flag inicial deberia ser falsy')
      .toBe(false)
    expect(countMapClicks(), 'un motor nuevo debe publicar los clics').toBe(1)
  })

  it('suppressClicks() with no argument silences them', () => {
    engine.suppressClicks()
    expect(countMapClicks(), 'suppressClicks() deberia silenciar los clics').toBe(0)
  })

  it('a drawing tool turns it off, as the tools need', () => {
    const tools = new ToolManager(engine, {})
    engine.suppressClicks(true)

    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    // A tool must receive its clicks, so activation clears the flag.
    expect(engine._clickSuppressed, 'activar una herramienta debe liberar los clics')
      .toBe(false)
    tools.deactivate()
  })

  it('releasing the tool does not silence the map again', () => {
    // Nothing restores the flag, so once a tool has been used the map stays
    // live. That is why the bug only shows on a page where no drawing tool has
    // been picked — and why it looks intermittent.
    const tools = new ToolManager(engine, {})
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    tools.deactivate()

    expect(countMapClicks(), 'tras usar una herramienta el mapa debe seguir vivo')
      .toBe(1)
  })
})
