# Tutorials (day one)

Each guide: what it does → how we use it → the common task → gotchas. Two demo spaces are seeded on
every boot (`python -m aurum.demo --refresh`, see `../modules/demo.md`): **Demo personal** (`demo-personal`,
a clean personal-only fixture — accounts, a semimonthly salary, four fixed payments, budgets, a goal and
three months of movements) for the personal guides, and `demo-mx` (a synthetic MX freelancer, months
2026-06..08) for the Avanzado guides. Follow along at `http://localhost:5024/?ws=demo-personal` or
`?ws=demo-mx`. Never use a demo for your own data; your space is `personal`.

Personal first (the everyday screens — simple mode):

| Guide | Covers |
|---|---|
| [personal-finance.md](personal-finance.md) | **Start here.** Day-one checklist (backup first), Empezar → + Agregar → Movimientos → Cuentas → Presupuesto → Metas → Ajustes |
| [mi-dinero.md](mi-dinero.md) | Mi dinero: pagos fijos a mano, "Pagado" / "Registrar" / "Deshacer", the Monday-first calendar, income streams, the one "Disponible hasta el <fecha>" |
| [quick-capture.md](quick-capture.md) | Captura rápida (atajo): one line → an editable movement on a chosen account; CSV import needs an account; what stays behind Avanzado |

Avanzado (tax, documents, research, automation — visible when the space is in advanced mode):

| Guide | Covers |
|---|---|
| [documents-cfdi.md](documents-cfdi.md) | Getting invoices in (XML/ZIP drop, SAT sync with a local e.firma), the payment-method semantics |
| [month-close-prefill-audit.md](month-close-prefill-audit.md) | The MX month close for the freelancer regime: the expected SAT prefill and the five kinds of difference |
| [research.md](research.md) | Asking the law assistant, reading citation cards and trust tiers, when it abstains |
| [law-tracker.md](law-tracker.md) | Watch: what changed, impact tags, rule-update proposals |
| [mcp-server.md](mcp-server.md) | Connecting an MCP client (for example Claude Desktop) or a local agent to Aurum's tools |
| [telegram-nudges.md](telegram-nudges.md) | Daily digest to Telegram from cron or any scheduler; Telegram quick-add (lands in the Inbox) |
| [workflows.md](workflows.md) | Automating month close / weekly review with YAML workflows, scheduling, and LLM-drafted proposals |

Before you write or change any copy in the app or these guides, read
[`../modules/design-system.md`](../modules/design-system.md) (vocabulary, banned words). Everything Aurum
shows is decision support. Filing outputs are watermarked DRAFT; Aurum never signs or transmits anything
to SAT or the IRS.
