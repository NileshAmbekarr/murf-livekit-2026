'use client';

import { useCallback, useEffect, useState } from 'react';
import { MediaDeviceFailure, type Room, RoomEvent } from 'livekit-client';

/**
 * Microphone availability, which for a voice health line is the difference
 * between a working service and a blank screen.
 *
 * Denial arrives at two different moments — when the caller presses start, and
 * when they revoke access mid-call — so both paths are handled here.
 */

/** Why the microphone is unusable. Narrower than livekit's own enum, on purpose. */
export type MicFailureKind = 'denied' | 'notFound' | 'inUse';

/**
 * Classify an error as a microphone problem, or `null` if it is not one.
 *
 * Careful: `MediaDeviceFailure.getFailure()` returns `Other` for *any* value with
 * a `name` property, which every `Error` has. A LiveKit token failure or a
 * dropped network would therefore come back as `Other`. Treating that as a
 * microphone fault would tell the caller to unblock a microphone that was never
 * the problem, so only the three specific device failures count here and
 * everything else is deliberately `null`.
 */
export function classifyMicError(error: unknown): MicFailureKind | null {
  switch (MediaDeviceFailure.getFailure(error)) {
    case MediaDeviceFailure.PermissionDenied:
      return 'denied';
    case MediaDeviceFailure.NotFound:
      return 'notFound';
    case MediaDeviceFailure.DeviceInUse:
      return 'inUse';
    default:
      return null;
  }
}

export interface MicPermissionState {
  /** The current microphone problem, or null when there isn't one. */
  failure: MicFailureKind | null;
  /** Classify and record an error. Returns the kind, or null if unrelated. */
  report: (error: unknown) => MicFailureKind | null;
  clear: () => void;
}

export function useMicPermission(room: Room | undefined): MicPermissionState {
  const [failure, setFailure] = useState<MicFailureKind | null>(null);

  const report = useCallback((error: unknown) => {
    const kind = classifyMicError(error);
    if (kind) setFailure(kind);
    return kind;
  }, []);

  const clear = useCallback(() => setFailure(null), []);

  // Mid-call revocation: the caller can turn the microphone off in site settings
  // while the room is still up, and the call would otherwise go quietly deaf.
  useEffect(() => {
    if (!room) return;

    const onDeviceError = (error: Error) => {
      const kind = classifyMicError(error);
      if (kind) setFailure(kind);
    };

    room.on(RoomEvent.MediaDevicesError, onDeviceError);
    return () => {
      room.off(RoomEvent.MediaDevicesError, onDeviceError);
    };
  }, [room]);

  return { failure, report, clear };
}

/** Whether the browser has already decided about the microphone. */
export type MicReadiness = 'unknown' | 'granted' | 'denied' | 'prompt';

/**
 * A best-effort read of the existing microphone permission, so the intake card
 * can say up front that the caller will be asked.
 *
 * Feature-detected: the Permissions API's `microphone` name is unsupported in
 * Firefox and Safari, where this stays `unknown` and simply shows nothing.
 */
export function useMicReadiness(): MicReadiness {
  const [readiness, setReadiness] = useState<MicReadiness>('unknown');

  useEffect(() => {
    let cancelled = false;
    let status: PermissionStatus | undefined;

    const sync = () => {
      if (!cancelled && status) setReadiness(status.state as MicReadiness);
    };

    void (async () => {
      try {
        status = await navigator.permissions?.query({
          name: 'microphone' as PermissionName,
        });
        if (!status) return;
        sync();
        status.addEventListener('change', sync);
      } catch {
        // Unsupported browser. Staying 'unknown' is the right answer.
      }
    })();

    return () => {
      cancelled = true;
      status?.removeEventListener('change', sync);
    };
  }, []);

  return readiness;
}
