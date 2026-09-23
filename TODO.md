# TODO — Reestructuración del Mapa (unificación)

- [x] 1. LeafletMap.vue: conectar props openSkyPoints/openSkyTrack/selectedOpenSkyIcao24 y renderizar aviones en vivo + trayectoria
- [x] 2. LeafletMap.vue: exponer `getMap()` con defineExpose
- [x] 3. LeafletMap.vue: emitir `live-aircraft-selected` al hacer clic en un avión
- [x] 4. MapView.vue: integrar tracking en vivo (useOpenSkyLive) + panel de vuelos en vivo/estado
- [x] 5. MapView.vue: agregar búsqueda de vuelos, coordenadas del cursor
- [x] 6. MapView.vue: agregar import/export GeoJSON/KML/KMZ y búsqueda de aeropuertos/coordenadas
- [x] 7. MapView.vue: unificar persistencia bajo una sola clave
- [x] 8. router/index.js: eliminar ruta /mapas-avanzado y import de MapasView
- [x] 9. App.vue: eliminar ítem de navegación "Mapas Avanzado"
- [x] 10. Verificar build con `npm run build` (118 módulos, sin errores)

## Corrección posterior (pantallas vacías al navegar)
- [x] 11. Crear `serve_spa.py`: servidor estático SPA-friendly con fallback a index.html + proxy de API al backend (8000)
- [x] 12. `start.bat`: en modo prod usar `serve_spa.py` (con SPA fallback y proxy) en lugar de `python -m http.server` (que no maneja rutas SPA)
- [x] 13. Frontend sirviéndose correctamente en http://localhost:5173 (SPA fallback 200 en /expedientes, proxy /api ok)
