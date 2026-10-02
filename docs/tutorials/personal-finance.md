# Tus finanzas en Aurum: Empezar → + Agregar → Movimientos → Cuentas → Presupuesto → Metas

**Qué hace.** Aurum lleva tu dinero de todos los días a mano: tus cuentas, lo que entra, lo que sale,
cuánto puedes gastar hasta tu próximo ingreso, un presupuesto por categoría y tus metas. Todo lo que
ves lo calcula código a partir de lo que tú capturas; ningún modelo de lenguaje decide un monto. Lo
fiscal, las facturas y la investigación siguen ahí, pero un clic más lejos, bajo **Avanzado**.

**Cómo lo usamos.** Un espacio por persona. El tuyo se llama `personal`; el de muestra es
**Demo personal** (`demo-personal`) y sirve para ver las pantallas llenas antes de capturar nada. Las
pantallas del día a día son las ocho del menú: **Inicio · Movimientos · Pagos e ingresos fijos ·
Presupuesto · Metas · Cuentas · Categorías · Ajustes**, y al final **Avanzado**. Con menos de 960 px el menú se vuelve una barra inferior
**Inicio · Movimientos · [+] · Cuentas · Más**.

---

## Día uno (lista de verificación)

1. **Respalda antes de tocar nada.** Dos formas:
   - En la app: **Ajustes › Copia de seguridad › "Descargar copia de seguridad"** te da un zip con las
     cuentas, movimientos, pagos fijos y metas del espacio; **"Exportar movimientos (CSV)"** te da el rango
     de meses que elijas.
   - Todo el directorio de datos (recomendado antes de un día uno real):
     ```
     curl -X POST http://localhost:5024/api/backup     # → {"path": "backups/aurum-<fecha>.zip", "size": …, "sha256": …}
     curl http://localhost:5024/api/backups            # lista, la más nueva primero
     ```
     La receta completa y cómo restaurar están en [`../OPERATIONS.md`](../OPERATIONS.md) ("Backup" y
     "Restore"). Restaurar es **siempre a un directorio nuevo y vacío**, nunca encima del que está en uso:
     ```
     uv run python scripts/restore.py backups/aurum-<fecha>.zip --into /ruta/a/un-directorio-nuevo
     ```
2. **Abre tu espacio.** Entra a `http://localhost:5024/?ws=personal` (la app recuerda el espacio; después
   basta con `http://localhost:5024/`). Nunca uses un demo para tus datos: los demos traen movimientos de
   muestra y aparecen agrupados bajo "Demos" en el selector de espacio y en Ajustes › Espacios.
3. **Ve a Empezar.** `http://localhost:5024/empezar/` o, si tu Inicio está vacío, el botón **"Empezar
   (5 minutos)"**. Son cuatro pasos a mano; cada uno se guarda con su propio botón y puedes volver
   cuando quieras con **"Empezar de nuevo"**, al final de Ajustes.
4. **Qué escribes y en qué orden.**
   1. **Agrega tus cuentas** — una por cada lugar donde vive tu dinero: banco (Cuenta de cheques o
      Ahorro), Efectivo, Tarjeta de crédito, Préstamo. Para el banco y el efectivo responde
      **"¿Cuánto tienes hoy?"**; para una tarjeta o un préstamo responde **"¿Cuánto debes hoy?"** con lo
      que debes **como número positivo** (Aurum le pone el signo). En una tarjeta agrega Día de corte, Día
      de pago y Límite de crédito; en un préstamo, Tasa anual (%) y Plazo en meses. Guarda con
      **"Guardar cuenta"**.
   2. **¿De dónde viene tu dinero?** — elige una plantilla ("Sueldo quincenal (15 y 30)", "Sueldo mensual"
      o "Freelance o variable"), di **a qué cuenta llega**, cuánto recibes ya con descuentos y qué días te
      pagan ("Último día" cuenta como el 31). **"Guardar ingreso"**.
   3. **Tus pagos fijos** — Renta, Luz, Internet, Streaming, Tarjeta: nombre, qué es, monto, la cuenta
      que paga, cada cuánto y qué día. Si el monto cambia cada mes (luz, agua, tarjeta) marca **"¿Varía
      cada mes?"**: al pagarlo te pedirá el monto real. **"Guardar pago fijo"**.
   4. **Tus primeros gastos** — **"Agregar un gasto"** o las fichas Súper / Comida fuera / Transporte
      abren la ventana **+ Agregar** con el comercio ya puesto. Tres movimientos bastan para ver cómo
      funciona. Desde cualquier pantalla la tecla **`n`** abre esa misma ventana.
5. **Cómo compruebas que quedó bien.**
   - **Cuentas**: arriba, por moneda, "Tienes", "Debes" y "Neto"; cada tarjeta o préstamo dice
     "Debes $X". Nunca se suman pesos con dólares: con dos monedas ves dos filas.
   - **Movimientos**: "Entró", "Salió" y "Neto" del mes vienen del servidor sobre *todos* los movimientos
     del filtro, no solo los que ves en pantalla.
   - **Inicio**: el número grande es **"Disponible hasta el <fecha>"**: lo que tienes en cuentas, menos
     los pagos fijos que faltan antes de tu próximo ingreso, menos el presupuesto que aún no gastas,
     menos un colchón. Si todavía no capturas un ingreso verás **"Lo que tienes hoy"** y una liga para
     agregarlo. "¿Cómo se calcula?" muestra cada resta.

---

## Las pantallas, en el orden en que las usas

### Empezar (`/empezar/`)

Cuatro pasos con su propio botón de guardar; **"Siguiente"** y **"Lo hago después"** avanzan sin guardar
nada más. Las palomitas vienen del servidor: si ya tienes cuentas, el paso aparece hecho aunque entres
de nuevo. Al terminar, **"Listo. Así se ve tu dinero"** muestra "Lo que tienes hoy" (la suma de tus cuentas
líquidas en tu moneda) y te manda a Inicio o a tu primer gasto.

### + Agregar (la ventana de captura)

La misma ventana desde el botón **+ Agregar**, la tecla `n`, el botón `[+]` de la barra inferior, la
ficha "Agregar movimiento aquí" de una cuenta y "Registrar" en Mi dinero. Pestañas **Gasto · Ingreso ·
Transferencia**; el **Monto va primero y ya con el foco**; luego categoría (con tus "Frecuentes" arriba),
la cuenta con la que pagaste, la fecha (Hoy / Ayer) y, bajo **"Más detalles"**, comercio o quién, nota,
etiquetas y **"Dividir en categorías"** (las partes deben sumar exactamente el monto). **Enter guarda**;
**Ctrl+Enter** guarda y deja la ventana abierta para el siguiente; **Esc** cancela. Cada guardado avisa
"Guardado · −$250.00 · Comida fuera" con **Deshacer**. Los montos se escriben sin signo: el tipo decide.

**Foto del recibo.** En *Gasto*, **"Leer foto del recibo (atajo)"** abre la cámara o tu galería. Aurum guarda
la foto (sin la ubicación ni los datos del teléfono), la lee y llena **solo lo que está vacío**: el monto
(la línea TOTAL, nunca SUBTOTAL, IVA ni CAMBIO), el comercio, la categoría y la fecha del ticket. Lo que
no está seguro dice **"revisa"**, y **"¿Cómo lo leímos?"** muestra por qué y el texto que leyó. Nada se
guarda hasta que presionas **Guardar**; el movimiento queda con su foto (📎 en Movimientos). Si corriges
la categoría, la próxima vez que fotografíes ese mismo comercio Aurum usa la que elegiste. Si el ticket ya
estaba registrado (misma foto, o mismo día y monto), te avisa antes de guardarlo dos veces. Las fotos
HEIC del iPhone todavía no: en Ajustes › Cámara › Formatos elige "Más compatible".

### Movimientos (`/movimientos/`)

El mes actual (flechas o `?period=2026-09`), búsqueda por comercio o nota, filtros por cuenta, categoría
y tipo. Las filas van por día con un subtotal del día (se omite si ese día mezcla monedas). Una fila con
el chip "Pago fijo", "Importado", "Factura" o "Nómina" te dice de dónde salió; las que otro módulo escribió
directo en el libro (por ejemplo una nómina) no se editan aquí ("Se capturó desde … y no se puede cambiar
aquí."), pero sí se **duplican**. Para
cambiar algo abre la fila (o ⋯ › Editar): es la misma ventana + Agregar. Selecciona varias y usa
**"Poner categoría"** para reetiquetar de golpe; las transferencias y las bloqueadas se saltan y el
aviso te dice cuántas. Borrar pide confirmación y deja **Deshacer** unos segundos: nada se destruye, el
movimiento se anula y deja de contar.

### Cuentas (`/cuentas/`)

Una tarjeta por cuenta agrupada en Efectivo y bancos · Tarjetas de crédito · Préstamos · Inversiones ·
Otras. Acciones en ⋯: **Editar** (nombre, banco y los datos de tarjeta o préstamo; el saldo inicial no
se edita), **Ajustar saldo** (escribe el saldo real de hoy y Aurum registra la diferencia como un ajuste:
"tus movimientos no cambian") y **Archivar** (desaparece de las listas y del patrimonio, no se borra
nada, "Ver archivadas" la trae de vuelta). **"Agregar movimiento aquí"** abre + Agregar con esa cuenta
elegida.

### Presupuesto (`/presupuesto/`)

Un límite por categoría y mes. Cada fila dice "Gastado $X de $Y · queda $Z" y cambia de tono en
**"Casi al límite"** (80 %) y **"Excedido"** (100 %); tocarla abre Movimientos filtrado a esa categoría.
Arriba, "Presupuestado", "Gastado" y **"Presupuesto restante"** (este número **no** es el Disponible de
Inicio: aquí solo cuenta el presupuesto). El mes nuevo empieza vacío con un botón **"Copiar del mes
anterior"**; repetirlo no duplica nada. "Pasar lo que sobre al mes siguiente" arrastra el sobrante.

### Metas (`/metas/`)

Ahorro, Fondo de emergencia, Pagar una deuda o Una compra, cada una ligada a **una cuenta tuya**: el
avance es el saldo de esa cuenta. Con fecha límite te dice "Necesitas ahorrar $X al mes para el <fecha>";
**"Cómo va"** proyecta a qué ritmo llegas. **"Aportar"** abre + Agregar en Transferencia hacia la cuenta de
la meta con el monto mensual ya puesto. En una meta de deuda ligada a un préstamo, **"Simular"** te dice
cuántos meses antes terminarías con un pago extra. La plantilla "Fondo de emergencia (3 meses de
gastos)" prellena el monto con tus gastos de los últimos tres meses; "Viaje" solo el tipo y el nombre.

### Ajustes (`/settings/`)

**Perfil** (nombre y moneda del espacio, idioma de la app, idioma de los avisos) · **Apariencia**
(Sistema / Claro / Oscuro) · **Categorías** (crear, editar, esconder o borrar; una categoría con
movimientos solo se esconde) · **Modo** (Simple o Avanzado, o módulos sueltos) · **Copia de
seguridad** (zip del espacio y CSV de movimientos) · **Espacios** (usar, esconder, crear; el espacio
`personal` está protegido y nada en Aurum borra un espacio). Al final, fuera de las secciones,
**"Empezar de nuevo"** (vuelve al asistente) y **"Restablecer preferencias"** (olvida espacio, idioma, tema
y clave guardados en este navegador; tus datos no cambian).

---

## Lo que conviene saber

- **Nada se borra.** Un movimiento borrado se anula y se puede deshacer; una cuenta se archiva; un pago
  fijo queda como cancelado; un espacio se esconde. No hay botón de "borrar todo".
- **Deudas en positivo.** Escribes lo que debes como número positivo (5000) en tarjetas y préstamos, en
  el alta y en Ajustar saldo; la app muestra "Debes $5,000.00" y el patrimonio neto ya lo resta.
- **Un solo "Disponible".** Solo Inicio y Mi dinero lo muestran, y es el mismo número. Presupuesto dice
  "Presupuesto restante", que es otra cosa.
- **Dos monedas no se suman.** Cada cuenta tiene su moneda; los totales van por moneda.
- **Las horas de la noche.** La fecha de hoy es la de tu reloj local, no la de UTC: un gasto capturado a
  las 20:00 en la Ciudad de México cae en el día correcto.
- **Atajos, siempre marcados.** "Captura rápida (atajo)" e "importa un estado de cuenta (atajo)" existen
  y crean movimientos editables normales, pero solo en modo Avanzado — ver
  [quick-capture.md](quick-capture.md). Lo primero siempre es capturar a mano.
- **Mi dinero** (pagos fijos, calendario, "Ya lo pagué", el Disponible por dentro) tiene su propia guía:
  [mi-dinero.md](mi-dinero.md).
