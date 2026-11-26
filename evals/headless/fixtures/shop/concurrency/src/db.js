// A key-value store with asynchronous I/O, like a remote database: every call yields before it answers.
const rows = new Map();
const io = () => new Promise((resolve) => setImmediate(resolve));

export const db = {
  async get(key) {
    await io();
    return rows.get(key) ?? 0;
  },
  async put(key, value) {
    await io();
    rows.set(key, value);
  },
};
