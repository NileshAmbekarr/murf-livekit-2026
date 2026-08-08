'use client';

import { useCallback, useEffect, useState } from 'react';
import { type Room, RoomEvent } from 'livekit-client';

/**
 * Listens for the escalation signal the agent publishes when
 * `escalate_to_emergency_care` fires.
 *
 * Day 2 built a two-layer emergency escalation and none of it was visible on
 * screen. The caller heard "call one zero eight" and had to hold four digits in
 * their head while frightened. This puts the same number in front of them as a
 * link they can press.
 *
 * The numbers come from the payload rather than being hardcoded here, because
 * the backend reads them from the same constants the spoken script uses — so
 * the screen and the voice cannot drift apart.
 */

/** Must match `ESCALATION_TOPIC` in backend/src/agent.py. */
export const ESCALATION_TOPIC = 'sehat.escalation';

export interface EscalationNotice {
  /** Ambulance number, e.g. "108". */
  ambulance: string;
  /** General emergency number, e.g. "112". */
  emergency: string;
  /** True when the caller is pregnant or has a newborn. */
  maternal: boolean;
}

export interface EscalationSignalState {
  notice: EscalationNotice | null;
  clear: () => void;
}

export function useEscalationSignal(room: Room | undefined): EscalationSignalState {
  const [notice, setNotice] = useState<EscalationNotice | null>(null);

  const clear = useCallback(() => setNotice(null), []);

  useEffect(() => {
    if (!room) return;

    const onData = (
      payload: Uint8Array,
      _participant?: unknown,
      _kind?: unknown,
      topic?: string
    ) => {
      if (topic !== ESCALATION_TOPIC) return;

      try {
        const body = JSON.parse(new TextDecoder().decode(payload));
        if (body?.type !== 'escalation') return;

        setNotice({
          ambulance: String(body.ambulance),
          emergency: String(body.emergency),
          maternal: Boolean(body.maternal),
        });
      } catch {
        // A malformed signal must never take the call down with it. The caller
        // is still being told the number out loud, which is the path that counts.
      }
    };

    room.on(RoomEvent.DataReceived, onData);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
    };
  }, [room]);

  return { notice, clear };
}
