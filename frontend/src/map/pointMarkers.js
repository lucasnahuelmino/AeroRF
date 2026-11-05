export const POINT_MARKERS = Object.freeze([
  {
    id: 'marker',
    label: 'Marcador general',
    description: 'Ubicación sin clasificación específica.',
    icon: '/iconos/marker.svg',
  },
  {
    id: 'fm',
    label: 'FM',
    description: 'Torre de radiodifusión FM.',
    icon: '/iconos/fm.svg',
  },
  {
    id: 'tprs',
    label: 'TPRS',
    description: 'Simbología TPRS existente.',
    icon: '/iconos/tprs.svg',
  },
  {
    id: 'antenna',
    label: 'Antena RF',
    description: 'Antena o mástil radioeléctrico.',
    icon: '/iconos/antenna.svg',
  },
  {
    id: 'radiobase',
    label: 'Radiobase celular',
    description: 'Infraestructura de red móvil.',
    icon: '/iconos/radiobase.svg',
  },
  {
    id: 'repeater',
    label: 'Repetidora',
    description: 'Estación de retransmisión.',
    icon: '/iconos/repeater.svg',
  },
  {
    id: 'monitoring',
    label: 'Estación de monitoreo',
    description: 'Sitio de monitoreo del espectro.',
    icon: '/iconos/monitoring.svg',
  },
  {
    id: 'poi',
    label: 'Punto de interés',
    description: 'Ubicación de interés geográfico.',
    icon: '/iconos/poi.svg',
  },
  {
    id: 'otro',
    label: 'Otro',
    description: 'Clasificación técnica no catalogada.',
    icon: '/iconos/otro.svg',
  },
])

const MARKERS_BY_ID = new Map(POINT_MARKERS.map((marker) => [marker.id, marker]))

export function getPointMarker(id) {
  return MARKERS_BY_ID.get(id) || MARKERS_BY_ID.get('marker')
}
