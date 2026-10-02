/**
 * The MCP tool surface of `aurum/mcp_server`, as a static list.
 *
 * It lives outside the mock on purpose: the Tools screen shows this in a real build too, and
 * importing it from lib/mock would drag the whole fake API into the production bundle. The
 * browser cannot reach the MCP server (stdio/HTTP on AURUM_MCP_PORT), so this is documentation
 * of what the server exposes, not a probe of it.
 */
import type { McpTool } from './types';

export const MCP_TOOLS: McpTool[] = [
  { name: 'search_law', description: 'Búsqueda citada sobre el corpus de ley (MX/US).' },
  { name: 'get_law_changes', description: 'Cambios publicados desde una fecha, con ámbito e impacto.' },
  { name: 'calc_tax', description: 'ISR e IVA del periodo con el cálculo desglosado y las versiones de regla.' },
  { name: 'prefill_diff', description: 'Diferencias entre Aurum y el prellenado esperado del SAT.' },
  { name: 'quick_add', description: 'Captura una transacción en una línea; llega a la Bandeja.' },
  { name: 'post_entry', description: 'Registra un asiento en el libro de Beancount.' },
  { name: 'balances', description: 'Saldos por cuenta a una fecha.' },
  { name: 'financial_statement', description: 'Estado de resultados o balance del periodo.' },
  { name: 'goal_status', description: 'Avance y proyección de una meta.' },
  { name: 'budget_status', description: 'Estado de los presupuestos del mes.' },
];
