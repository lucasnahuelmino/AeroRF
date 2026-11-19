# Manual de usuario — AeroRF

Guía inicial para operar AeroRF. Para detalles técnicos, ver `MANUAL.md`,
`README.md` y `AERORF_ARCHITECTURE.md`.

---

## 1. Inicio rápido

### Arrancar la aplicación (doble clic)

1. Haga doble clic en `start.bat` en la carpeta del proyecto.
2. Se abren dos ventanas (backend y frontend) y el navegador en
   `http://localhost:5199`.
3. El backend queda en `http://127.0.0.1:8010`; la salud se verifica en
   `http://127.0.0.1:8010/health`.

### Detener

Doble clic en `start.bat` con argumento `stop`, o ejecute en consola:
```
start.bat stop
```

### Modos adicionales

- `start.bat test` — ejecuta la suite de pruebas.
- `start.bat build` — construye el frontend para producción.

### Requisitos

- Python 3.11+ con entorno virtual `.venv`.
- Node.js 18+.
- (Opcional) credenciales OpenSky en `.env` para vuelos en vivo.

---

## 2. Secciones de la aplicación

### Mapa (pantalla principal)

Todo el trabajo geográfico ocurre aquí.

- **Barra superior:** navegación (Mapa · Calculadora RF), estado del backend
  y OpenSky, lockup ENACOM.
- **Panel izquierdo:** cuatro pestañas — Herramientas, Capas, Vuelos,
  Aeropuertos.
- **Mapa central:** Leaflet con capas, objetos, aeronaves.
- **Panel derecho (inspector):** propiedades, geometría, notas, historial.
- **Coordenadas/escala/hora:** en la parte inferior del mapa.

### Calculadora RF

Motor de cálculo de frecuencias sin mapa. Dos modos:
- **Armónicos:** tabla de armónicas contra la referencia.
- **Intermodulación:** productos IM2/IM3/IM5/IM7.

Arranca vacía. Use «Cargar ejemplo» para datos de prueba (marcados como
«DATOS DE EJEMPLO»).

---

## 3. Herramientas del mapa

Se activan desde la barra superior. La barra muestra siempre una instrucción.

| Herramienta | Uso | Crea |
|---|---|---|
| Seleccionar | Clic en objeto | — |
| Punto | Clic en mapa | Punto (con fuente FM/TPRS/Otra) |
| Anotación | Clic + texto | Nota geolocalizada |
| Línea | Clic en vértices, Enter para cerrar | Polilínea con longitud |
| Polígono | Igual que línea, mín. 3 vértices | Área |
| Traza | Clic para agregar vértices | Recorrido con longitud acumulada |
| Círculo | Clic centro, mover para radio | Círculo exacto (NM y km) |
| Radial | Clic origen, mover para azimut/longitud | Radial sobre círculo máximo |
| Medir | Clic en A, clic en B | Lectura (no objeto) |
| Cobertura | Dibujar contorno | Polígono de cobertura |

**Atajos:** `Esc` cancela, `Enter` confirma, `Retroceso` quita último vértice,
clic derecho abre menú contextual, doble clic cierra línea/polígono.

---

## 4. Capas

17 capas, cada una con visibilidad, opacidad, bloqueo y cantidad de objetos.
El bloqueo impide editar el contenido.

---

## 5. Vuelos

- Búsqueda en OpenSky (requiere credenciales en `.env`).
- Lista de seguimiento de hasta 5 aeronaves.
- Grabación de trayectorias y reproducción.
- Correlación espacial con objetos RF.

---

## 6. Aeropuertos

105 aeródromos publicados de 8 países más sitios propios (EAVA, CCTE,
aeroclubs). Filtro por país y distancia desde un aeropuerto a cualquier punto.

---

## 7. Calculadora RF

1. Ingrese la frecuencia de referencia (MHz).
2. Agregue emisoras (manual o por CSV).
3. Pulse «Calcular».
4. Revise los resultados en Armónicos o Intermodulación.
5. Guarde el análisis en el historial propio (sin expedientes).
6. Exporte como CSV o JSON.

**Importar CSV:** admite `,` y `;`, BOM, comillas, multilínea, decimales con
punto o coma. Se muestra un resumen antes de confirmar.

**Guardar análisis:** pulse «Guardar análisis actual» en el panel Historial.
El análisis queda con identidad propia y se puede consultar, asociar a un
objeto GIS o eliminar.

---

## 8. Exportar mapa a PNG

Pulse el botón de exportación. Se genera un PNG del área cartográfica visible,
incluyendo la atribución. Si el servidor de mosaicos bloquea por CORS o algún
recurso no se cargó, la exportación falla con un mensaje explícito (no se
descarga un PNG incompleto).

---

## 9. Panel contextual (inspector)

Muestra el objeto seleccionado: propiedades, geometría, notas e historial.
Es append-only: las notas se conservan para siempre. Cada cambio queda
registrado con su valor anterior.

Si un objeto viejo trae un expediente asociado (dato histórico), se muestra,
pero ya no se ofrece asociación.

---

## 10. Preguntas frecuentes

**No me aparecen vuelos en vivo.**
Revise el punto de OpenSky en la barra superior. Configure
`OPENSKY_CLIENT_ID` y `OPENSKY_CLIENT_SECRET` en `.env` y reinicie el backend.

**La trayectoria de un avión no crece.**
Se refresca cada 30 segundos mientras el vuelo sigue en curso. Si aterrizó, la
línea queda fija: es correcto.

**¿Dónde queda lo que dibujo?**
Todo objeto se guarda en la base de datos, con su historial. Los aeropuertos
y sitios de referencia no: son datos de referencia.

**¿Y si borro algo por error?**
AeroRF guarda una copia de la base de datos en `respaldos/` cada vez que
arranca. Se conservan las 10 más recientes.

---

## 11. Soporte

- Documentación técnica: `AERORF_ARCHITECTURE.md`
- Estado del proyecto: `RETOMAR.md`
- Historial de cambios: `AERORF_CHANGELOG.md`
- Manual completo: `MANUAL.md`
