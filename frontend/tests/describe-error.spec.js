/**
 * tests/describe-error.spec.js
 * ────────────────────────────
 * P0-02: `describeError` con el 409 nuevo del borrado de expedientes.
 *
 * El backend pasa a contestar 409 en `DELETE /expedientes/{id}` cuando
 * hay objetos GIS vinculados. Regla de contrato: el cliente se actualiza
 * en el mismo commit. `detail` en español ya tiene prioridad (lo que
 * muestra la pantalla en el caso normal), y este spec deja medido que el
 * 409 **sin** detail tampoco cae en «Error 409» crudo, más los dos
 * estados de OpenSky que ya tenían mensaje propio.
 */
import { describe, expect, it } from 'vitest'

import { describeError } from '@/api/client'

describe('describeError', () => {
  it('prefiere el detail del backend, venga como venga', () => {
    const e = {
      response: {
        status: 409,
        data: { detail: 'No se puede borrar el expediente 5: objetos vinculados.' },
      },
    }
    expect(describeError(e)).toBe(
      'No se puede borrar el expediente 5: objetos vinculados.',
    )
  })

  it('un 409 sin detail no dice «Error 409»', () => {
    const e = { response: { status: 409, data: {} } }
    expect(describeError(e)).not.toBe('Error 409')
    expect(describeError(e)).toMatch(/conflicto/i)
  })

  it('los estados de OpenSky siguen con su mensaje conocido', () => {
    expect(
      describeError({ response: { status: 429, data: {} } }),
    ).toContain('Límite de créditos')
    expect(
      describeError({ response: { status: 503, data: {} } }),
    ).toContain('OpenSky no está configurado')
  })
})
