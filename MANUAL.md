# Manual de uso — AeroRF

Guía de las dos secciones activas y las herramientas del mapa. Para quien
opera la herramienta, no para quien la mantiene.

> Para instalar y para el diseño interno, ver **[README.md](README.md)** y
> **[AERORF_ARCHITECTURE.md](AERORF_ARCHITECTURE.md)**.

---

## Antes de empezar

Dos cosas que conviene tener presentes al trabajar:

**Todo dato declara de dónde viene.** Cada punto, cada tramo de trayectoria y
cada valor guardado lleva su procedencia: *observado*, *histórico*, *en vivo*,
*calculado* o *introducido por el usuario*. Cuando un dato no existe, AeroRF
muestra «dato no disponible». No rellena, no estima, no completa. Es lo que
hace que un expediente suyo sea defendible.

**La correlación no es causalidad.** La herramienta informa qué tan cerca está
una fuente de interferencia de una aeronave. Que dos cosas estén cerca no
significa que una moleste a la otra, y ningún informe de AeroRF sugiere lo
contrario. Lo mismo vale para la calculadora: una coincidencia matemática no
es evidencia de interferencia.

---

## La barra superior

Está presente en **todas** las secciones. Es fina a propósito, para no robarle
altura al mapa.

| Elemento | Qué hace |
|---|---|
| Marca **AeroRF** | Vuelve al mapa, que es la pantalla principal. |
| **Mapa · Calculadora RF** | Navegación. El elemento activo lleva un filo celeste. |
| **Tres puntos** | Estado: backend, OpenSky, canal de vuelos en vivo. Verde = bien, ámbar = atención, gris = inactivo. Pasá el cursor sobre cada uno para el detalle. |
| **ENACOM** | Lockup institucional: Dirección Nacional de Control y Fiscalización. |

> **Expedientes** ya no es una sección de la aplicación: quedó retirado como
> dependencia funcional en AeroRF 2.6. Los datos históricos y el API legado
> (`/expedientes/*`) siguen intactos en el backend para clientes históricos.

---

## Sección 1 — Mapa

La pantalla principal. Todo el trabajo geográfico ocurre acá.

### Estructura

```
┌──────────────────────────────────────────────────────────────┐
│  barra superior (48 px)                                       │
├──────────────────────────────────────────────────────────────┤
│  herramientas │              MAPA              │ inspector    │
│  Capas        │                               │              │
│  Vuelos       ├───────────────────────────────┤              │
│  Aeropuertos  │  coordenadas · escala · hora   │              │
│               ├───────────────────────────────┤              │
│               │  línea de tiempo (opcional)    │              │
└──────────────────────────────────────────────────────────────┘
```

Los dos paneles laterales se pliegan y se arrastran por su borde: el mapa toma
todo el ancho que le dejen. Los anchos quedan recordados.

### Las cuatro pestañas del panel izquierdo

**Herramientas.** Opciones de la herramienta activa: unidades, radio, longitud,
azimut, colores. Los valores que escriba son los que se usan.

**Capas.** Diecisiete capas, cada una con visibilidad, opacidad, bloqueo y
cantidad de objetos. El bloqueo impide editar lo que contiene.

**Vuelos.** Búsqueda en OpenSky, lista de seguimiento de hasta 5 aeronaves,
grabación de trayectorias y reproducción.

**Aeropuertos.** Lo publicado (105 aeródromos de 8 países) sumado a los
sitios de su propia lista —EAVA, CCTE, aeroclubs—, con filtro por país y
distancia desde un aeropuerto a cualquier punto del mapa. Los aeropuertos
se dibujan con un avión: para cambiar el dibujo basta con reemplazar
`frontend/public/iconos/aeropuerto.svg` (mismo nombre, ver `LEEME.txt`).

### El panel derecho: inspector

Muestra el objeto seleccionado: propiedades, geometría, notas e historial. Es
append-only: las notas se conservan para siempre y no se sobrescriben, y cada
cambio de un campo queda registrado con su valor anterior.

Si un objeto viejo trae un expediente asociado (dato histórico), el inspector
lo muestra, pero ya no ofrece ninguna operación de asociación: un objeto nuevo
no tiene, ni necesita, expediente.

**Aquí es donde está toda la información de un objeto.** Al hacer clic en un
objeto no aparece ninguna ventana sobre el mapa: el mapa queda despejado y los
datos se leen en este panel, que además permite editarlos. Un clic ya selecciona;
el doble clic también, y conviene para líneas finas como un radial, donde el
blanco es de tres píxeles.

---

## Las diez herramientas del mapa

Se activan desde la barra superior. La barra muestra siempre una instrucción
de la herramienta activa.

### Herramientas de captura

| Herramienta | Cómo se usa | Qué crea |
|---|---|---|
| **Seleccionar** | Clic en un objeto para inspeccionarlo. Clic en vacío para deseleccionar. | — |
| **Punto** | Un clic en el mapa. | Un punto. |
| **Anotación** | Un clic, después escribí el texto. | Una nota geolocalizada. |

**La fuente del punto.** Al elegir **Punto**, las opciones muestran
**Fuente del punto**: Sin fuente (punto simple), FM, TPRS u Otra fuente. La
fuente se dibuja con su propio icono en el mapa, y también se cambia después
desde el inspector, sobre un punto ya dibujado. Los dibujos viven en
`frontend/public/iconos/` (`fm.svg`, `tprs.svg`, `otro.svg`): para cambiar
uno, reemplace el archivo conservando el nombre (instrucciones en
`LEEME.txt`).

### Herramientas de forma

| Herramienta | Cómo se usa | Qué crea |
|---|---|---|
| **Línea** | Clic en cada vértice. Doble clic o `Enter` para cerrar. `Esc` cancela. | Una polilínea, con su longitud. |
| **Polígono** | Igual que la línea, mínimo 3 vértices. | Un área. |
| **Traza** | Clic para agregar vértices a una traza abierta. | Un recorrido con longitud acumulada. |

**Se acumulan.** Dibujar una segunda línea no modifica la primera: cada forma
se guarda como un objeto independiente y todas conviven. Lo mismo con los
polígonos, las trazas y los círculos. Puede dibujar tantas líneas como necesite.

**Retroceso** quita el último vértice mientras dibuja.

### Herramientas de medida sobre el mapa

| Herramienta | Cómo se usa | Qué crea |
|---|---|---|
| **Círculo** | Clic para fijar el centro, después mueva el puntero para definir el radio. `Enter` confirma. | Un círculo exacto, con el radio en NM y km. |
| **Radial** | Clic para el origen, mueva para fijar azimut y longitud. | Un radial sobre el círculo máximo de la Tierra, no una recta en el plano. |
| **Medir** | Clic en A, clic en B. Clic sucesivos para multipunto. | Una lectura, no un objeto. Guardala si la quiere conservar. |
| **Cobertura** | Dibuje el contorno de un área. | Un polígono de cobertura. |

**El radio tecleado se respeta.** Si escribe 20 NM en el panel de herramientas
y hace clic sin mover el puntero, obtiene 20 NM. El puntero ajusta; no pisa lo
que escribió.

**Unidades.** NM, km o metros, a elección. Las distancias se muestran siempre en
las dos unidades principales, porque un expediente puede pedir una y el otro
lector entender la otra.

---

## Exportar el mapa a PNG

El botón de exportación genera una imagen PNG del área cartográfica visible.

- Se exporta el mapa base, los objetos dibujados y los marcadores, **incluida
  la atribución** del mapa base.
- Se excluye la cromática de la interfaz (controles de zoom y paneles).
- Si el servidor de mosaicos bloquea la composición por CORS, o algún recurso
  de marcador no se cargó o no se pudo dibujar, la exportación **falla con un
  mensaje explícito** y no se descarga un PNG incompleto.

---

## Sección 2 — Calculadora RF

Motor de cálculo de frecuencias, sin mapa. Para el trabajo de gabinete.

La calculadora **arranca vacía**: sin frecuencia de referencia y sin emisoras,
con el mensaje «Ingresá una frecuencia de referencia y agregá las emisoras que
quieras analizar.». No hay datos precargados; los datos de ejemplo se cargan
con el botón secundario **Cargar ejemplo**, que marca la pantalla con la
etiqueta **DATOS DE EJEMPLO** y se puede quitar con **Quitar ejemplo**.

- **Armónicos:** hasta qué frecuencia llega un equipo, y a qué nivel.
  Fórmulas: `f_n = f_0 × n`, `Δf_kHz = |f_n - f_ref| × 1000`,
  `f_0 = f_ref / n`.
- **Intermodulación:** qué combinaciones de dos frecuencias generan una tercera
  no deseable, y cuál de ellas cae dentro de una banda aeronáutica.
- **Bandas aeronáuticas:** referencia de las bandas de vuelo.

Los resultados se expresan como diferencias en kHz y estados (Exacta / En
tolerancia / Fuera de tolerancia). No hay probabilidades: AeroRF no afirma
causalidad.

### Importar emisoras desde CSV

La importación acepta archivos CSV reales:

- separadores `,` y `;`;
- UTF-8 con BOM;
- campos entrecomillados, comillas escapadas (`""`) y campos multilínea;
- encabezados alternativos: `nombre`, `emisora`, `estación`, `frecuencia`,
  `frecuencia_mhz`, `mhz`, `observaciones`, `localidad`, `provincia`,
  `identificador` (y sus equivalentes en inglés);
- decimales con punto o coma, según el separador de campos.

Antes de importar se muestra un resumen (filas leídas, válidas, a importar,
duplicadas, rechazadas) y los motivos de rechazo, con la opción de confirmar
o cancelar. No se duplican emisoras sin aviso.

### Guardar un análisis

1. Haga el cálculo y, si quiere, seleccione el resultado que le interesa.
2. Pulse **Guardar análisis actual** en el panel **Historial de análisis**.
   El análisis se guarda con sus parámetros y sus resultados completos, con
   identidad propia: **no depende de ningún expediente**.
3. El aviso cuenta lo que devolvió el backend (número de análisis y cantidad
   de productos). Si algo falla, lo dice en rojo y no se guardó nada.

Los análisis guardados aparecen en el mismo panel, con fecha, modo, referencia,
emisoras y productos. Con **Ver resultados** se restaura la corrida en la tabla
sin recalcular; con **Eliminar** se borra (con confirmación). También se pueden
exportar como CSV y JSON.

La asociación opcional a un objeto GIS (fuente RF, evento RF o antena) se
admite vía el API (`objeto_id` en `POST /rf/analisis`), cuando corresponda.

---

## Flujo de trabajo recomendado

**Para una denuncia de interferencia:**

1. **Ubicar.** Abra el mapa. Active la capa **Aeropuertos** para tener el
   contexto de qué estación está cerca.
2. **Medir.** Cree un círculo alrededor de la estación afectada, con el radio
   que sea pertinente. El radio queda en NM y km.
3. **Documentar.** Cree el punto de la fuente, con sus características RF en
   el inspector.
4. **Registrar vuelos.** En **Vuelos**, busque el tráfico que atraviesa la
   zona y agregue hasta 5 aeronaves a la lista de seguimiento. Pulse
   **Trayectoria** para ver su ruta.
5. **Cotejar.** La correlación espacial muestra qué fuentes están dentro del
   radio. **Lea la advertencia:** proximidad no es causalidad.
6. **Calcular.** Use la **Calculadora RF** para armónicos e intermodulación;
   guarde el análisis en el historial si lo necesita.
7. **Exportar.** Exporte el mapa a PNG o los datos a GeoJSON, KML o CSV.

**Para un estudio de protección:**

1. Delimite el área con un **círculo** o un **polígono**.
2. Use **Medir** para las distancias críticas dentro del área.
3. Compare contra la capa de **aeropuertos** para tener la referencia más cercana.

---

## Atajos de teclado

| Tecla | Acción |
|---|---|
| `Esc` | Cancela la herramienta activa, la medición y el menú contextual. |
| `Enter` | Confirma el dibujo en curso. |
| `Retroceso` | Quita el último vértice. |
| Clic derecho | Abre el menú contextual en el mapa. |
| Doble clic | Cierra una línea o un polígono. |

---

## Preguntas frecuentes

**No me aparecen vuelos en vivo.**
Revise el punto de OpenSky en la barra superior. Ámbar significa que faltan
credenciales: configure `OPENSKY_CLIENT_ID` y `OPENSKY_CLIENT_SECRET` en `.env`
y reinicie el backend. Sin configurarlo, AeroRF funciona para todo lo demás.

**La trayectoria de un avión no crece.**
La trayectoria en vivo se refresca cada 30 segundos mientras el vuelo sigue en
curso. Si el avión aterrizó, la línea queda fija: es correcto, el vuelo
terminó. Los vuelos históricos no se refrescan, porque su trayectoria no puede
cambiar.

**No puedo guardar un círculo.**
Verifique que el radio sea mayor que cero. Un círculo de radio cero no es una
medida, y AeroRF no lo guarda.

**¿Dónde queda lo que dibujo?**
Todo objeto del mapa se guarda en la base de datos, con su historial. Los
aeropuertos y los sitios de su lista **no**: son datos de referencia —
publicados y su propia lista — y se redibujan desde los archivos en cada
arranque. Por eso no puede editarlos ni borrarlos, y es intencional: un
punto de referencia no es una medición suya.

**¿Y si borro algo por error?**
AeroRF guarda una copia de la base de datos en la carpeta `respaldos`, dentro de
la carpeta del proyecto, **cada vez que arranca** y antes de escribir nada. Se
conservan las 10 más recientes; las más viejas se reemplazan solas. Para volver
a un estado anterior: cierre AeroRF, renombre el `aerorf.db` actual y ponga en su
lugar la copia que quiera, quitándole la fecha del nombre. La copia se hace con
el propio SQLite, de modo que incluye lo último escrito aunque el servidor
estuviera corriendo.

**Los datos de OpenSky no coinciden con lo que veo en el radar.**
La resolución de los tracks de OpenSky no es de un punto por segundo. Un vuelo
típico tiene un punto cada decenas de segundos, y más separados cuando el avión
no cambia de rumbo. La respuesta de la API indica cuántos puntos hay y cada
cuánto: lea ese dato antes de concluir que falta información.

**¿AeroRF guarda mis búsquedas?**
Guarda los objetos que usted crea, con su historial. Las consultas a OpenSky
consumen créditos de la cuenta configurada en `.env`, por eso la aplicación
limita la frecuencia y avisa cuando alcanza el límite.

---

## Soporte

Documentación técnica: `AERORF_ARCHITECTURE.md`.
Estado del proyecto: `RETOMAR.md`.
Historial de cambios: `AERORF_CHANGELOG.md`.
