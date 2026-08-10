'use client';

import { useCallback, useEffect, useState } from 'react';
import { type Room, RoomEvent } from 'livekit-client';

/**
 * Listens for the nearby-facility list the agent publishes when
 * `find_nearest_facility` fires.
 *
 * An address is the classic thing nobody can hold in their head — the Day 5 task
 * says as much — so the names and distances the agent speaks also land on
 * screen. Same mechanism as `useEscalationSignal`, deliberately: that pattern is
 * already proven end to end.
 */

/** Must match `FACILITIES_TOPIC` in backend/src/agent.py. */
export const FACILITIES_TOPIC = 'sehat.facilities';

export interface Facility {
  name: string;
  /** Already a speakable word ("health centre"), not a raw OSM tag. */
  kind: string;
  distanceKm: number;
  lat: number;
  lon: number;
  address: string;
}

export interface FacilityNotice {
  items: Facility[];
  /** Date the map data was current, `YYYY-MM-DD`. May be empty. */
  asOf: string;
}

export interface FacilitySignalState {
  notice: FacilityNotice | null;
  clear: () => void;
}

export function useFacilitySignal(room: Room | undefined): FacilitySignalState {
  const [notice, setNotice] = useState<FacilityNotice | null>(null);

  const clear = useCallback(() => setNotice(null), []);

  useEffect(() => {
    if (!room) return;

    const onData = (
      payload: Uint8Array,
      _participant?: unknown,
      _kind?: unknown,
      topic?: string
    ) => {
      if (topic !== FACILITIES_TOPIC) return;

      try {
        const body = JSON.parse(new TextDecoder().decode(payload));
        if (body?.type !== 'facilities' || !Array.isArray(body.items)) return;

        setNotice({ asOf: String(body.as_of ?? ''), items: body.items as Facility[] });
      } catch {
        // A malformed card must never take the call down. The caller is being
        // told the same thing out loud, which is the part that matters.
      }
    };

    room.on(RoomEvent.DataReceived, onData);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
    };
  }, [room]);

  return { notice, clear };
}
