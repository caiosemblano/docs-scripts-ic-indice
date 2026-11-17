const brlFormatter = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const brlCompactFormatter = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  notation: 'compact',
  maximumFractionDigits: 1,
});

const numFormatter = new Intl.NumberFormat('pt-BR', {
  maximumFractionDigits: 2,
});

export function formatBRL(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return brlFormatter.format(value);
}

export function formatBRLCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return brlCompactFormatter.format(value);
}

export function formatPct(value: number | null | undefined, digits = 2, showPlus = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = showPlus && value > 0 ? '+' : '';
  return `${sign}${value.toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return numFormatter.format(value);
}

export function formatDateBR(iso: string | null | undefined): string {
  if (!iso) return '—';
  const parts = iso.slice(0, 10).split('-');
  if (parts.length !== 3) return iso;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

export const STRATEGY_LABELS: Record<string, string> = {
  acquirers_multiple: "The Acquirer's Multiple",
  magic_formula: 'The Magic Formula',
};
