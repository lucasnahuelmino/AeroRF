# Punto de retorno — AeroRF

**Fecha:** 2026-09-26
**Estado:** funcional y verificado en ejecución. La interfaz ya fue probada
montándola de verdad, no solo compilándola.

---

## Para arrancar de nuevo

```powershell
cd C:\Users\lucas\OneDrive\Escritorio\VSCODE\AeroRF

# Backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010

# Frontend (otra terminal)
cd frontend
$env:VITE_API_TARGET="http://127.0.0.1:8010"
npm run dev
```

El puerto 8000 lo tiene el proyecto hermano `rni-app-4.0`; AeroRF usa **8010**.

> **Ojo:** Vite escucha en `::1` (IPv6). Si `http://127.0.0.1:5173` no
> responde, probá `http://localhost:5173`.

---

## Lo que cambió en esta sesión

Se hizo un chequeo completo de funcionalidad, con foco en vuelos en tiempo
real. Aparecieron **seis defectos reales**, todos verificados con un test que se
comprobó revirtiendo el arreglo.

### Los bugs

| # | Defecto | Efecto |
|---|---------|--------|
| B1 | El drafter emite `latlngs`, la API declara `geometry`. Nada traducía | **Líneas y polígonos se guardaban con cero puntos.** La petición era exitosa, volvía un id, y aparecía un objeto vacío |
| B2 | La geometría no se validaba al escribir | Un anillo mal formado hacía que **todo** `GET /map/objects` devolviera 500: un objeto malo vaciaba el mapa |
| B3 | `from sqlalchemy import func` importado **dentro** de una función | Era un nombre local → `PUT /map/layers/{id}` daba 500. **Ninguna capa se podía mostrar ni ocultar** |
| B4 | `/live-track` usaba otro camino que `/track` | Sin `provenance_counts` y sin procedencia por punto: la leyenda nunca se llenaba |
| B5 | La trayectoria se cargaba una vez y quedaba congelada | Un vuelo en vivo no crecía mientras se miraba |
| B6 | `bindLabel` sobre un `circleMarker` | El método no existe: pedir etiquetas de aeropuerto lanzaba en cada símbolo |

B1 es el peor de los tres primeros porque fallaba **en silencio**: todo parecía
funcionar.

### Lo nuevo

- **Capa de aeropuertos**: 67 aeródromos de 8 países en
  `frontend/src/data/airports.js`, **generados** por `tools/build_airports.py`
  desde OurAirports. Conmutable, con filtro por país y etiquetas ICAO.
  No se persiste: son hechos publicados, no trabajo del operador.
- **Distancia desde aeropuerto**: código ICAO o IATA, clic en el destino, y la
  línea con la distancia en m/km/NM y el rumbo.
- **Capas propias** `lines` y `polygons`: compartían `traces`, así que no se
  podía mostrar una sin las demás.
- **La trayectoria en vivo crece**: sondeo de 30 s mientras el vuelo sigue
  airborne, que se detiene solo al aterrizar o al cambiar de aeronave. Un vuelo
  histórico no se sondea: su track es inmutable.

### Por qué el archivo de aeropuertos es generado

La versión escrita a mano tenía cuatro códigos ICAO duplicados, cuatro IATA
duplicados, dos pares de coordenadas idénticas con nombres distintos, y
coordenadas que no pertenecían a ningún aeródromo. Todo parecía verosímil.

`SAAD` no existe: el de Rosario es `SAAR`. Verificado contra la fuente, y el
generador informa los códigos que pidió y no encontró.

---

## Verificación

```powershell
# Python — 357 tests, ~9 s, sin backend
.\.venv\Scripts\python.exe -m pytest -m "not integration" -q

# Python — 7 tests, requiere el backend en 8010
.\.venv\Scripts\python.exe -m pytest -m integration -q

# Frontend — 136 tests
cd frontend
npm test

# Paridad JS <-> Python — 675 comprobaciones
node tests/geo_parity.mjs
```

**Totales:** 357 + 7 Python, 136 frontend, 675 de paridad, 78 E2E por HTTP.

### Contra OpenSky real, en la última corrida

- 12.991 aeronaves en `/flights/live`, 99,4% con posición.
- Trayectorias en vivo de 79 a 97 puntos, todas con posición y con
  `provenance: live`.
- WebSocket: la aeronave se mueve entre mensajes con altitud, velocidad y
  rumbo reales.

### Las siete herramientas, por API

`punto`, `linea`, `polígono`, `círculo`, `radial`, `traza` y `anotación` crean
objetos con geometría correcta, cada uno en su capa, y **conviven sin pisarse**:
crear una línea no altera las anteriores.

---

## Lo que falta

1. **Ver el shell con ojos humanos.** jsdom detecta fallos de ejecución, no de
   apariencia: un panel que se solapa o un texto que se sale sigue sin
   detector.
2. **Nada está commiteado.** 90+ archivos en el working tree.
3. **Rotar `client_secret` de OpenSky** si esta conversación se guarda o se
   comparte, y actualizar `.env`.
4. **Alembic**, cuando haya que migrar datos de verdad. Nota: las capas nuevas
   (`lines`, `polygons`) se sembraron solas, sin migración.
5. **Autenticación de usuarios**, cuando se pida.

---

## Decisiones que conviene no revertir sin motivo

- **FastAPI, no Flask.** El spec pedía Flask, pero el repo ya usaba FastAPI +
  Uvicorn (el servidor ASGI que el propio spec exige) y Flask no hace
  WebSocket nativo.
- **`MapObject` como raíz única** de todo objeto espacial del usuario.
- **Geometría guardada dos veces**: `Float` lat/lon indexados + columna JSON
  `geometry`.
- **Los datos de referencia no van en la base.** Aeródromos y ENACOM son hechos
  publicados: se redibujan de un archivo, no ocupan filas y no se confunden con
  el trabajo del operador.
- **Ningún dato inventado.** Se borró el módulo de vuelos fabricados completo.
- **Tailwind está activo de verdad.** `styles.css` no tenía directivas
  `@tailwind`, así que *ninguna* clase utilitaria existía: el logo se dibujaba a
  1024 px y el mapa a la mitad de su ancho. Hay un test que lee el CSS
  construido para que no vuelva a pasar.
- **Limitación de grabación, documentada:** el muestreo ocurre en el bucle de
  sondeo del WebSocket, que solo corre con un cliente conectado. "Grabar vuelo"
  no graba nada con el navegador cerrado.

---

## La lección de fondo

La documentación de OpenSky no coincide con su formato en el cable. Los
fixtures construidos a partir de la documentación pasaban mientras el código
estaba roto en producción. El mismo tipo de bug apareció cinco veces: 17 campos
en vez de 18, camelCase en vez de minúsculas, altitudes imposibles, créditos
desperdiciados, y ahora el doble módulo de JavaScript.

**Un documento de API no es un contrato. El único contrato es lo que el servidor
devuelve de verdad, y lo único que prueba una interfaz es ejecutarla.**
