# Mi dinero — pagos fijos, "Ya lo pagué", calendario y tu Disponible

**Qué hace.** **Mi dinero** (`/money/`) junta lo que se repite: tus pagos fijos y suscripciones, tus
ingresos, un calendario del mes y un pronóstico de saldo. Con eso calcula **un solo número**,
**"Disponible hasta el <fecha>"**, que es el mismo que ves en Inicio. Todo lo calcula código
(sumas y fechas); no hay un modelo de lenguaje decidiendo montos.

**Cómo lo usamos.** Primero a mano: cada pago fijo lo escribes tú con su formulario. Detectarlos en
un estado de cuenta existe, pero como atajo y solo en modo Avanzado (**Configurar**). Las pestañas en
modo simple son **Resumen · Pagos fijos · Ingresos · Calendario · Flujo**; **Plan** y **Configurar**
aparecen solo en Avanzado.

---

## Antes de empezar

Necesitas al menos una cuenta (Cuentas o el asistente Empezar). Sin pagos fijos ni ingresos, Resumen te
lo dice — "Aquí van tus pagos fijos y tus ingresos" — con dos botones: **"Agregar mi ingreso"** y
**"Agregar un pago fijo (atajo)"**. Nada se detecta solo en ese punto.

---

## Pagos fijos (a mano primero)

**"+ Nuevo pago fijo"** abre el formulario:

| campo | qué pones |
|---|---|
| Nombre | como lo reconoces tú: Netflix, Renta, Luz |
| ¿Qué es? | Suscripción · Servicio · Renta o hipoteca · Préstamo o tarjeta · Seguro · Otro |
| Monto | lo que se cobra; si cambia cada vez, marca **"¿Varía cada mes?"** (luz, agua, tarjeta) |
| Cuenta que paga | por nombre, nunca una ruta contable |
| Categoría | la de gastos que le corresponde |
| Cada cuánto | Cada semana · Cada 2 semanas · Cada mes · Cada 2 meses · Cada 3 meses · Cada 6 meses · Cada año · Cada {n} días |
| Qué día | 1–30 o **"Último día del mes"** (un cargo del 31 cae el 28/29/30 según el mes) |
| Próximo pago | por defecto hoy; Aurum lo mueve al día que le diste (Renta "día 1" creada el 19 queda para el 1 del mes siguiente) |
| Se paga solo · Es indispensable | para el pronóstico y el plan |

Guarda con **"Guardar pago fijo"**. Si ya existe uno con ese nombre te avisa: "Ya tienes Netflix —
editar el existente · Guardar de todas formas".

La lista muestra Nombre · Cada · Próximo · Cuenta · Monto · Estado; por defecto ves los que están **"En
curso"** y puedes cambiar a "Todos". Abrir una fila muestra su ficha: las últimas ocurrencias (pagado,
no detectado, omitido), el historial de precios y, si está ligado a un préstamo, el avance. Ahí puedes
**Editar**, **Pausar** ‖ **Reanudar**, **Cancelar** (con una nota: a quién llamaste, folio) o **Quitar**.
Quitar no borra: "Queda como cancelado: sale de tu lista y de tu calendario, pero no se borra. Tus
movimientos no cambian."

**El atajo.** Debajo de la lista, cerrado, está **"Atajo: escríbelo en una línea"** — por ejemplo
`netflix 219 mensual día 15` — que te muestra "Así lo entendimos" antes de guardar. Es lo mismo que el
formulario, solo más rápido de escribir.

---

## "Ya lo pagué"

En Resumen (**Próximos 7 días**) y en Inicio (**Próximos pagos**) cada cargo trae un botón según su
tipo:

| el cargo… | botón | qué pasa |
|---|---|---|
| tiene monto fijo | **"Pagado"** | un toque: se marca pagado y Aurum registra el movimiento por ti (chip "Pago fijo" en Movimientos), con **Deshacer** |
| varía cada mes | **"Registrar"** | se abre **+ Agregar** con nombre, cuenta y fecha ya puestos; escribes el monto real, Enter, y el pago queda marcado |
| es un ingreso | **"Ya llegó"** | igual que Pagado, del lado que entra |
| ya está pagado u omitido | **"Deshacer"** | vuelve a pendiente |

En el **Calendario**, tocar un día y luego el cargo abre la misma ficha con **"Ya lo pagué"**, **"Este
mes no"** (lo omite solo esta vez) y **"Deshacer"**. Los cortes y pagos de tarjeta y las mensualidades de
préstamo se muestran pero no se marcan ("Este cargo lo calcula la app; no hay nada que marcar.").

**Deshacer, con honestidad.** Deshacer solo anula el movimiento que Aurum creó por ti al tocar
"Pagado". Si el movimiento lo registraste tú ("Registrar", o uno que ya tenías y Aurum reconoció), se
queda: verás "Sigue como pagado: el movimiento lo registraste tú y se queda. Para deshacerlo, bórralo
desde Movimientos."

En Inicio, si un pago fijo no tiene cuenta, "Pagado" no puede registrar el movimiento y te manda por el
camino de "Registrar".

---

## Calendario

La rejilla del mes empieza en **lunes** (en inglés, en domingo). Cada día muestra hasta tres cargos y
un "+N"; abajo, **"Sale $X · Entra $Y"** con los totales del mes. Con menos de 768 px el calendario es una
agenda por día, sin rejilla. Cambia de mes con las flechas o `?period=2026-10`. Un mes sin nada dice
"Nada programado en <mes>".

---

## Ingresos

La pestaña **Ingresos** lista tus fuentes de ingreso (la misma que llena el asistente Empezar):
**"Nuevo ingreso"** pregunta qué tipo
es (Sueldo, Honorarios / freelance, Renta, Pensión, Inversiones, Otro), **a qué cuenta llega**, cuánto
recibes (ya con descuentos) y cada cuánto: "Dos veces al mes" con dos días de pago ("Último día" = 31),
"Cada mes", "Cada 14 días" o "Cada semana" con el día de la semana, "Una vez al año" o "Irregular" con
la fecha del próximo pago. Marca **"Ya no llega"** cuando se acabe. En cada fila, **"Registrar
ingreso"** abre + Agregar ya lleno y **"Historial"** muestra lo esperado contra lo recibido: "Llegó",
"Llegó menos", "No llegó", "Se omitió", "No llegó todavía".

---

## Un solo Disponible

El número grande de Resumen (y de Inicio) es **"Disponible hasta el <fecha>"**: cuánto puedes gastar
de aquí a tu próximo ingreso sin dejar de pagar nada. Se arma con cuatro partes, que ves debajo:

| parte | qué es |
|---|---|
| **Lo que tienes en cuentas** | tus cuentas líquidas: bancos y efectivo |
| **− Pagos fijos pendientes** | lo que vence (o ya se venció hace poco) antes de tu próximo ingreso y sigue sin pagarse |
| **− Presupuesto que falta** | lo que aún no gastas de tu presupuesto del mes (sin contar las categorías que ya cubre un pago fijo) |
| **− Colchón** | un margen por si algo se atrasa; por defecto 10 % de tus pagos fijos del mes |

**"¿Cómo se calcula?"** abre la explicación paso a paso: "Lo que tienes en cuentas líquidas", "Hasta tu
próximo ingreso", "Pagos fijos antes de esa fecha", "Presupuesto que falta por gastar", "Colchón" y, como
último renglón, "Libre para gastar", que es el resultado. No hay un segundo número: **Presupuesto** dice
"Presupuesto restante", que solo mira el presupuesto y no es el Disponible.

Si todavía no registras ningún ingreso, Inicio muestra **"Lo que tienes hoy"** en lugar del Disponible, con
una liga para agregarlo: sin fecha de próximo ingreso no hay "hasta cuándo".

---

## Flujo

Pronóstico a **30 · 60 · 90 días**: el saldo de hoy, más los ingresos y menos los pagos fijos proyectados,
día por día, en una gráfica. Tres datos: el mismo "Disponible hasta el <fecha>", **"Punto más bajo"** (qué
día y con cuánto te quedas, el aviso temprano de un mes apretado) y **"Colchón"** con un botón
**"Ajustar"** para fijarlo tú o volver a **"Usar el 10 % automático"**.

---

## Avisos

En Resumen, debajo de los próximos 7 días: subió o bajó un precio, termina una prueba, un pago no
detectado, un servicio duplicado, una renovación anual, "Ingreso por llegar", "Ingreso atrasado", "Cambió
tu ingreso" o "Cancelado, pero sigue cobrando". **"Entendido"** los descarta; un aviso descartado no vuelve
hasta que el hecho cambie.

---

## Cosas que conviene saber

- **Nada se borra.** Quitar un pago fijo lo deja como cancelado; un movimiento marcado por error se
  deshace; un ingreso que se acabó se marca "Ya no llega".
- **Monto variable = el calendario promete la fecha, no el monto.** Por eso "Registrar" te pide el real.
- **Fin de mes**: un cargo anclado al último día cae el 28/29/30/31 según el mes.
- **Plan y Configurar** (sobres Necesidades / Gustos / Ahorro / Deuda, detección desde tu estado de
  cuenta) viven en modo Avanzado: **Ajustes › Modo**.
- **Prueba con datos de ejemplo.** El espacio **Demo personal** trae cuentas, un sueldo quincenal, cuatro
  pagos fijos (Renta, Netflix, Telcel, Gym), presupuestos y una meta, con tres meses de movimientos; es
  la mejor forma de ver Mi dinero lleno antes de capturar lo tuyo. Nunca lo uses para tus datos.
