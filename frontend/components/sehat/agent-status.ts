import { type AgentState } from '@livekit/components-react';

/**
 * Bilingual status labels for the monitor readout.
 *
 * Hindi is romanised rather than in Devanagari here on purpose: the readout sits
 * next to a mono-spaced English label, and romanised Hindi is legible to the
 * widest set of callers, including those who speak Hindi but read only English
 * script.
 */
export interface StatusLabel {
  hindi: string;
  english: string;
  /** Which design token the state should be tinted with. */
  tone: 'idle' | 'active' | 'alert';
}

const LABELS: Record<string, StatusLabel> = {
  disconnected: { hindi: 'Band', english: 'Not connected', tone: 'idle' },
  initializing: { hindi: 'Taiyaar ho raha hai', english: 'Warming up', tone: 'idle' },
  connecting: { hindi: 'Jud raha hai', english: 'Connecting', tone: 'idle' },
  // The caller's speech is already being captured into the pre-connect buffer
  // here, even though the agent has not finished joining. Saying "not connected"
  // would tell them to stop talking when they should carry on.
  'pre-connect-buffering': { hindi: 'Sun raha hoon', english: 'Listening', tone: 'active' },
  idle: { hindi: 'Taiyaar', english: 'Ready', tone: 'idle' },
  listening: { hindi: 'Sun raha hoon', english: 'Listening', tone: 'active' },
  thinking: { hindi: 'Soch raha hoon', english: 'Thinking', tone: 'idle' },
  speaking: { hindi: 'Bol raha hoon', english: 'Speaking', tone: 'active' },
  failed: { hindi: 'Nahin jud paya', english: 'Could not connect', tone: 'alert' },
};

export function statusLabel(state: AgentState | undefined): StatusLabel {
  return LABELS[state ?? 'disconnected'] ?? LABELS.disconnected;
}

/** Formats elapsed milliseconds as mm:ss for the session record header. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = String(Math.floor(total / 60)).padStart(2, '0');
  const seconds = String(total % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}
