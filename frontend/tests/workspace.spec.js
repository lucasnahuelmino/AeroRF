import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useSystemStore } from '@/stores/system'

describe('workspace persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('opens the workspace by default and remembers the active panel', () => {
    const system = useSystemStore()

    expect(system.sidebarOpen).toBe(true)
    expect(system.leftPanel).toBe('tools')

    system.setPanel('layers')
    expect(system.leftPanel).toBe('layers')
    expect(localStorage.getItem('aerorf:workspace-section')).toBe('layers')
    expect(localStorage.getItem('aerorf:workspace-mode')).toBe('open')
  })

  it('keeps hover and sizing state in localStorage', () => {
    const system = useSystemStore()

    system.setWorkspaceWidth(420)
    system.setWorkspaceSide('right')
    system.setWorkspaceMode('collapsed')

    expect(system.sidebarWidth).toBe(420)
    expect(system.workspaceSide).toBe('right')
    expect(system.workspaceMode).toBe('collapsed')
    expect(localStorage.getItem('aerorf:workspace-width')).toBe('420')
    expect(localStorage.getItem('aerorf:workspace-side')).toBe('right')
    expect(localStorage.getItem('aerorf:workspace-mode')).toBe('collapsed')
  })
})
