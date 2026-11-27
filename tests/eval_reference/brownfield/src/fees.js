// Transfer fee: 1% of the amount, rounded half up to the cent, at least one cent. Integer arithmetic only.
export const FEE_ACCOUNT = 'sys:fees';

export function quoteFee(cents) {
  return Math.max(1, Math.floor((cents + 50) / 100));
}
