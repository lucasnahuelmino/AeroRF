# Punto de retorno — AeroRF

**Fecha:** 2026-09-30
**Estado:** funcional y verificado. Rama `main` en `origin/main`.

---

## 0.29.0 — El mapa toma el ancho que le dan

**Lo que pediste, hecho:** mapa más ancho, paneles más compactos, logo de
AeroRF más grande, y el de ENACOM con pie de página.

**El hallazgo que de verdad explica lo del ancho:** `MapEngine.invalidateSize()`
existía y **no lo llamaba nadie**. Abrir o cerrar un panel, o arrastrar su
borde, dejaba el mapa con el tamaño del momento de cargar. Medido: con el
sidebar abierto el contenedor mide 584 px y Leaflet sigue dibujando en 800 — los
216 px del sidebar muertos y el mapa aplastado a la izquierda. Por más que se
agranden los paneles, eso no se arregla: el mapa no se redibuja en el espacio que
le acaban de dar. Ahora un watcher le avisa.

**Verificado revirtiéndolo en el navegador**, porque en los tests de la cabecera
el shell del mapa no se monta: con el watcher neutralizado, 584 contra 800; con
el watcher, los cuatro estados cuadran.

Cambios: paneles de 268+300 a **216+256**; padding de tarjetas de `p-3` a
`p-2`; shell a `calc(100dvh - var(--brandbar-h) - var(--footerbar-h))` — con el
pie, el mapa se salía 74 px de la pantalla; logo de AeroRF de 30 a **34 px**; logo
de ENACOM oficial sobre **ficha blanca**, porque es RGB(11, 23, 66) y sobre la
barra oscura no se ve; pie nuevo de 26 px con el logo a 12 px y el nombre de la
Dirección, en todas las pantallas.

**342 tests frontend en verde.** Detalle en `AERORF_CHANGELOG.md`, sección
0.29.0.

---

## Dos cosas que conviene no volver a tropezar

**Un fixture con otra forma que el dato real hace pasar un test roto.** El
enganche al centro llevaba roto desde 0.27.0 y sus tests en verde: el fixture
armaba el círculo con `latlng` como **array**, y el código lo leía como
`centre[0]`, que en un array funciona y en el `{lat, lng}` que manda la API da
`undefined`. Es la misma trampa que el panel del punto central.

**Un test que cuelga el proceso no es una guarda.** Con el bucle de suscripción
puesto, la corrida no terminaba nunca en vez de fallar. La guarda se reescribió
para confirmar la figura a mano, sin pasar por el clic, y comparar la
*identidad* del handler: desuscribirse y volver a suscribirse deja el conteo en
uno igual, y el conteo no ve nada.

---

## Aviso sobre la memoria de la máquina

Si vitest se cuelga en «RUN» y no imprime nada, **no es el código**: es memoria.
La máquina bajó a 0,7 GB libres de 5,8 y mis ejecuciones en segundo plano
dejaban procesos vitest zombis. Matar primero:

```powershell
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -match "vitest" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Y no tocar el dev server del proyecto hermano `rni-app-4.0`, que tiene el 8000.

**Ojo también con `layout.spec.js`:** lee el CSS *construido*, así que hay que
reconstruir antes de correrlo o pasa con el `dist` viejo. Por eso una guarda
revertida puede dar verde sin motivo.

---

## Lo que queda pendiente

- **Las 16 filas duplicadas** de `aircraft_tracks` que ya había. No se borran: son
  datos del operador y la decisión es suya. El código ya no genera más.
- **Rotar `OPENSKY_CLIENT_SECRET`.** Sigue en claro en el historial de
  conversación de las últimas sesiones. Está en `.env`, ignorado por git, y en
  ningún archivo versionado.
- **`npm run lint` no funciona**: no hay configuración de ESLint en el
  repositorio, en ninguna rama ni en ningún commit. Figuraba como limpio y era
  falso. La comprobación real es el build.

---

## Verificación

| Suite | Estado |
|---|---|
| Frontend (vitest) | **342 pasan**, 27 archivos |
| Python (no integración) | **382 pasan**, 7 deseleccionadas |
| `tests/geo_parity.mjs` | 675 pasan |
| Build | limpio |

---

## Documentos

| Archivo | Qué es |
|---|---|
| `README.md` | Entrada al proyecto |
| `MANUAL.md` | Guía de uso para el operador |
| `AERORF_ARCHITECTURE.md` | Decisiones de diseño |
| `AERORF_CHANGELOG.md` | Cada cambio, con su motivo (0.16.0 → 0.29.0) |
| `docs/archive/AERORF_AUDIT.md` | Por qué se quitó cada parte del SIARI |
