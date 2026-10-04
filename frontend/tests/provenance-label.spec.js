/**
 * tests/provenance-label.spec.js
 * ──────────────────────────────
 * F2-08: la etiqueta de procedencia del frontend.
 *
 * `provenanceLabel` tiene su propia tabla en MapEngine.js — no lee el
 * vocabulario del backend —, así que un valor nuevo en `PROVENANCE_VALUES`
 * se le cae al piso y la UI pinta el crudo en inglés («imported»), justo
 * lo que avisa la auditoría. Aquí queda medido: el source del import de
 * GeoJSON se pinta en español, y los cinco originales siguen intactos.
 */
import { describe, expect, it } from 'vitest'

import { provenanceLabel } from '@/map/MapEngine'

describe('provenanceLabel', () => {
  it('dice «Importado» para el source del import de GeoJSON', () => {
    expect(provenanceLabel('imported')).toBe('Importado')
  })

  it('sigue etiquetando en español los cinco valores originales', () => {
    expect(provenanceLabel('observed')).toBe('Dato observado')
    expect(provenanceLabel('historical')).toBe('Dato histórico')
    expect(provenanceLabel('live')).toBe('Dato en vivo')
    expect(provenanceLabel('calculated')).toBe('Dato calculado')
    expect(provenanceLabel('user')).toBe('Introducido por el usuario')
  })

  it('sin valor devuelve el guion largo, no «undefined»', () => {
    expect(provenanceLabel('')).toBe('—')
    expect(provenanceLabel(undefined)).toBe('—')
  })
})
