# Captura rápida (atajo) y otras formas de meter movimientos

**Qué hace.** **Captura rápida** convierte una línea como `250 tacos comida` en un movimiento **normal
y editable** en la cuenta que tú elijas. No pasa por ninguna cola de revisión: lo que guardas queda en
Movimientos como cualquier otro, con el chip "Captura rápida" para que sepas de dónde salió.

**Cómo lo usamos.** Es un **atajo**, no el camino principal. El camino principal es **+ Agregar** (el
botón, la tecla `n`, o el `[+]` de la barra inferior); ver [personal-finance.md](personal-finance.md).
Captura rápida existe solo en **modo Avanzado** (Ajustes › Modo): ahí la abres con la tecla **`/`** o
desde el menú **⋯ › Captura rápida**.

**La tarea común.**

1. Abre la ventana **"Captura rápida (atajo)"**, escribe la línea y elige la cuenta (por defecto, la
   última que usaste en + Agregar):
   ```
   250 tacos comida
   1,200 uber trabajo
   $89.99 USD spotify suscripción
   ```
2. **"Revisar"** (o Enter) te muestra lo que entendió: Monto · Categoría · Cuenta · Comercio · Fecha,
   con las advertencias si algo no cuadra y un aviso de "baja confianza" cuando no está seguro (sin
   porcentajes). La categoría sale de tus propias categorías y sus alias (`comida` → *Comida fuera*).
3. **"Guardar movimiento"** (o Enter otra vez) lo guarda; verás el mismo aviso "Guardado · −$250.00 ·
   Comida fuera" con **Deshacer**. **"Descartar"** no guarda nada. Si editas el texto o cambias la cuenta,
   la vista previa se descarta y vuelves a revisar.

Sin una cuenta no hay captura: si no eliges una y no se puede adivinar por nombre, la app te pide
"Primero agrega una cuenta".

**Otras entradas, todas etiquetadas como atajo.**

- **Importar un estado de cuenta (CSV)** — el servidor pide **a qué cuenta** van las líneas y escribe
  movimientos editables con el chip "Importado"; una segunda importación del mismo archivo no duplica
  nada (se reconoce por fecha, monto y comercio). En la pantalla **Documentos** de Avanzado eliges la
  cuenta en el selector que está sobre la zona de subida; sin una cuenta elegida, el archivo no se
  envía. Las ligas "importa un estado de cuenta (atajo)" de Movimientos y del final de Empezar solo
  aparecen en Avanzado y llevan a Documentos.
- **Facturas (XML) y Telegram** — también en Avanzado, y estos sí pasan primero por la cola de
  revisión (Inbox) antes de tocar tus saldos; ver [documents-cfdi.md](documents-cfdi.md) y
  [telegram-nudges.md](telegram-nudges.md).
- **Foto de un ticket** — usa **+ Agregar › Gasto › "Leer foto del recibo (atajo)"** (ver
  [personal-finance.md](personal-finance.md)). La zona de foto de **Documentos** llama a una ruta que el
  API no tiene (`POST /api/ingest/{ws}/photo`), así que esa zona no funciona.
- **Pagos fijos** — en Mi dinero, "Pagado" registra el movimiento por ti (chip "Pago fijo"); ver
  [mi-dinero.md](mi-dinero.md).

**Cómo se ve por dentro** (para quien prefiera la API):

```
POST /api/ingest/{ws}/quickadd   {"text": "250 tacos comida", "account_id": "<id de la cuenta>"}                  → preview + warnings
POST /api/ingest/{ws}/quickadd   {"text": "250 tacos comida", "account_id": "<id>", "commit": true}                → entry (source "quickadd", editable)
POST /api/ingest/{ws}/bank/csv   multipart: file + account_id                                                      → {created, imported, skipped_duplicates, errors}
```

**Lo que conviene saber.**

- El intérprete es de reglas y determinista: mismas palabras, mismo resultado. No hay modelo de
  lenguaje en este camino.
- Lo que guarda Captura rápida se edita igual que cualquier movimiento: abre la fila en Movimientos.
- Los montos son decimales de punta a punta: `250` y `250.00` son lo mismo.
- En modo simple no verás ni `/` ni el menú de Captura rápida: es a propósito. Lo primero es capturar a
  mano.
