/**
 * A stable id for the person using this browser, so the agent can recognise a
 * returning caller.
 *
 * A real health line would key memory on a phone number. There is no telephony
 * here yet, and the stock token route mints a fresh random participant identity
 * on every call — which is why the agent could never remember anyone.
 *
 * So the browser keeps one. It is a random UUID with no personal information in
 * it: on its own it identifies a browser, not a person. That distinction is why
 * the agent still confirms the name out loud before acting on what it recalls —
 * on a shared household phone, which is exactly the setting this is built for,
 * the same browser can be two different people, and greeting the wrong one with
 * the other's health conditions would be a real harm.
 *
 * Clearing site data forgets them, and so does the agent's own `forget_me` tool.
 */

/** Must match `CALLER_ID_PREFIX` in backend/src/agent.py. */
export const CALLER_ID_PREFIX = 'sehat-caller-';

const STORAGE_KEY = 'sehat-sathi.caller-id';

function newCallerId(): string {
  const uuid =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36);

  return `${CALLER_ID_PREFIX}${uuid}`;
}

/**
 * The caller id for this browser, creating one on first use.
 *
 * Returns `undefined` when storage is unavailable — private browsing, or
 * storage blocked entirely. That is not an error: the caller simply stays
 * anonymous, the backend sees no durable id, and every call is treated as a
 * first call. Losing memory is a far better failure than blocking the call.
 */
export function getCallerId(): string | undefined {
  if (typeof window === 'undefined') return undefined;

  try {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing?.startsWith(CALLER_ID_PREFIX)) return existing;

    const fresh = newCallerId();
    window.localStorage.setItem(STORAGE_KEY, fresh);
    return fresh;
  } catch {
    return undefined;
  }
}

/**
 * Drop the local id, so this browser is unrecognised next time.
 *
 * The agent's `forget_me` tool deletes the stored record; this forgets the key
 * that pointed at it. Both exist because deleting only one leaves something
 * behind — a record nobody can reach, or a key pointing at nothing.
 */
export function clearCallerId(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored means nothing to clear.
  }
}
