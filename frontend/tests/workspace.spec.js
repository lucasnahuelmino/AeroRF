import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useSystemStore } from '@/stores/system'

describe('contextual workspace navigation', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('opens at the category home and persists category and task navigation', () => {
    const system = useSystemStore()

    expect(system.workspaceMode).toBe('open')
    expect(system.workspaceLevel).toBe('home')

    system.openWorkspaceCategory('layers')
    expect(system.workspaceLevel).toBe('category')
    expect(system.workspaceCategory).toBe('layers')

    system.openWorkspaceTask('layers', { category: 'layers', task: 'manage-layers' })
    expect(system.workspaceLevel).toBe('task')
    expect(system.workspaceTask).toBe('manage-layers')
    expect(localStorage.getItem('aerorf:workspace-section')).toBe('layers')
    expect(localStorage.getItem('aerorf:workspace-category')).toBe('layers')
    expect(localStorage.getItem('aerorf:workspace-task')).toBe('manage-layers')
    expect(localStorage.getItem('aerorf:workspace-mode')).toBe('open')
  })

  it('persists workspace mode, position, and width', () => {
    const system = useSystemStore()

    system.setWorkspaceWidth(420)
    system.setWorkspaceSide('right')
    system.setWorkspaceMode('collapsed')

    expect(system.workspaceWidth).toBe(420)
    expect(system.workspaceSide).toBe('right')
    expect(system.workspaceMode).toBe('collapsed')
    expect(localStorage.getItem('aerorf:workspace-width')).toBe('420')
    expect(localStorage.getItem('aerorf:workspace-side')).toBe('right')
    expect(localStorage.getItem('aerorf:workspace-mode')).toBe('collapsed')
  })

  it('routes selection into the inspector, respects a pinned context, and returns to the prior task', () => {
    const system = useSystemStore()
    system.openWorkspaceTask('flights', { category: 'flights', task: 'flight-operations' })

    expect(system.requestWorkspaceContext({ type: 'object', id: 41 })).toBe(true)
    expect(system.workspaceSection).toBe('inspector')
    expect(system.workspaceContext).toEqual({ type: 'object', id: 41 })
    expect(system.workspaceReturnTarget).toEqual({
      category: 'flights',
      level: 'task',
      section: 'flights',
      task: 'flight-operations',
    })

    system.toggleWorkspacePinned()
    expect(system.requestWorkspaceContext({ type: 'aircraft', icao24: 'ABC123' })).toBe(false)
    expect(system.workspaceContext).toEqual({ type: 'object', id: 41 })
    expect(system.pendingWorkspaceContext).toEqual({ type: 'aircraft', icao24: 'ABC123' })

    expect(system.inspectPendingWorkspaceContext()).toBe(true)
    expect(system.workspaceContext).toEqual({ type: 'aircraft', icao24: 'abc123' })
    expect(system.pendingWorkspaceContext).toBe(null)

    system.clearWorkspaceContext()
    expect(system.workspaceLevel).toBe('task')
    expect(system.workspaceSection).toBe('flights')
    expect(system.workspaceTask).toBe('flight-operations')
    expect(system.workspaceContext).toBe(null)
  })
})
