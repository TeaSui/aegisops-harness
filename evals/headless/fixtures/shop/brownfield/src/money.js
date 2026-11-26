// Amounts are integer cents everywhere. Only the edges (parsing input, printing output) know about decimals.
export function coded(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

export function parse(text) {
  if (typeof text !== 'string' || !/^\d+(\.\d{1,2})?$/.test(text)) throw coded('INVALID_AMOUNT', `not an amount: ${text}`);
  const [units, cents = ''] = text.split('.');
  return Number(units) * 100 + Number(cents.padEnd(2, '0'));
}

export function format(cents) {
  const sign = cents < 0 ? '-' : '';
  const absolute = Math.abs(cents);
  return `${sign}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, '0')}`;
}
