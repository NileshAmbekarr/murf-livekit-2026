'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { ConnectionState } from 'livekit-client';
import {
  type ReceivedMessage,
  useAgent,
  useSessionContext,
  useSessionMessages,
} from '@livekit/components-react';
import { type EscalationNotice, useEscalationSignal } from '@/hooks/useEscalationSignal';
import { type MicFailureKind, useMicPermission } from '@/hooks/useMicPermission';

/**
 * One place that knows what stage the consultation is at.
 *
 * Previously the whole interface was derived from `session.isConnected`, a single
 * boolean. A boolean cannot express "connecting" or "the call has ended", so
 * pressing start showed no feedback at all, and hanging up snapped the caller
 * back to a blank intake card with the transcript destroyed.
 *
 * This is a provider rather than a plain hook because three things have to
 * outlive the disconnect and be readable from several components at once: the
 * elapsed clock, the escalation latch, and the end-of-call snapshot that the
 * discharge slip is built from.
 */

export type ConsultationPhase = 'ready' | 'connecting' | 'live' | 'ended';

export interface ConsultationSummary {
  /** How long the caller and the agent were actually connected. */
  durationMs: number;
  /** Total turns in the record. */
  turnCount: number;
  /** How many of those were the caller's. */
  userTurnCount: number;
  /** Whether an emergency escalation fired during the call. */
  escalated: boolean;
  /** Emergency numbers as the agent gave them, when it escalated. */
  escalation: EscalationNotice | null;
  endedAt: number;
  /** The transcript, captured before the session store can clear it. */
  messages: ReceivedMessage[];
}

interface ConsultationContextValue {
  phase: ConsultationPhase;
  /** Milliseconds since the conversation went live; frozen once it ends. */
  elapsedMs: number;
  /** Set when the agent escalates. Never cleared mid-call — see below. */
  escalation: EscalationNotice | null;
  /** Populated on the live -> ended transition. */
  summary: ConsultationSummary | null;
  messages: ReceivedMessage[];
  /** The agent never arrived, or dropped out. */
  agentUnavailable: boolean;
  agentFailureReasons: string[];
  /** The room is up but the link is struggling. */
  isReconnecting: boolean;
  micFailure: MicFailureKind | null;
  clearMicFailure: () => void;
  /** The call was started without a microphone, so the caller is typing. */
  textOnly: boolean;
  /** Begin a call. Microphone problems are caught and reported, not thrown. */
  start: (options?: { microphone?: boolean }) => Promise<void>;
  end: () => Promise<void>;
  /** Clear the slip and start a fresh call. */
  restart: () => Promise<void>;
}

const ConsultationContext = createContext<ConsultationContextValue | undefined>(undefined);

export function useConsultation(): ConsultationContextValue {
  const value = useContext(ConsultationContext);
  if (!value) {
    throw new Error('useConsultation must be used inside a ConsultationProvider');
  }
  return value;
}

export function ConsultationProvider({ children }: { children: React.ReactNode }) {
  const session = useSessionContext();
  const agent = useAgent();
  const { messages } = useSessionMessages(session);
  const { notice: escalation, clear: clearEscalation } = useEscalationSignal(session.room);
  const mic = useMicPermission(session.room);

  const { connectionState, isConnected } = session;

  const [hasBeenLive, setHasBeenLive] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [summary, setSummary] = useState<ConsultationSummary | null>(null);

  const agentUnavailable = agent.state === 'failed';

  const phase = useMemo<ConsultationPhase>(() => {
    if (connectionState === ConnectionState.Connecting) return 'connecting';

    // The room connecting is not the same as the agent arriving. With the
    // pre-connect buffer on, the room comes up first and the agent joins after,
    // so `canListen` — not `isConnected` — is the point at which it is honest to
    // tell the caller to start speaking.
    if (isConnected) return agent.canListen ? 'live' : 'connecting';

    return hasBeenLive ? 'ended' : 'ready';
  }, [connectionState, isConnected, agent.canListen, hasBeenLive]);

  const isReconnecting =
    connectionState === ConnectionState.Reconnecting ||
    connectionState === ConnectionState.SignalReconnecting;

  // Start the clock when the conversation actually becomes usable, not when the
  // component mounts — the previous timer counted from mount and so was always
  // a little short.
  useEffect(() => {
    if (phase === 'live' && startedAt === null) {
      setStartedAt(Date.now());
      setHasBeenLive(true);
    }
  }, [phase, startedAt]);

  useEffect(() => {
    if (phase !== 'live' || startedAt === null) return;

    setElapsedMs(Date.now() - startedAt);
    const id = setInterval(() => setElapsedMs(Date.now() - startedAt), 1000);
    return () => clearInterval(id);
  }, [phase, startedAt]);

  // Held in a ref so the snapshot effect below depends only on `phase`. Reading
  // these as dependencies would rebuild the summary on every new message.
  const latest = useRef<{
    messages: ReceivedMessage[];
    escalation: EscalationNotice | null;
    startedAt: number | null;
  }>({ messages: [], escalation: null, startedAt: null });

  // The record is captured only while the call is live, and never overwritten
  // with an empty list. `useSessionMessages` empties its store on disconnect, and
  // the snapshot effect below runs *after* that — reading it there produced a
  // slip that said "Turns 0" for a conversation that plainly had turns.
  if (phase === 'live' && messages.length > 0) {
    latest.current.messages = messages;
  }
  latest.current.escalation = escalation;
  latest.current.startedAt = startedAt;

  useEffect(() => {
    if (phase !== 'ended') return;

    setSummary((existing) => {
      if (existing) return existing;

      const { messages: captured, escalation: notice, startedAt: began } = latest.current;
      const endedAt = Date.now();

      return {
        endedAt,
        durationMs: began === null ? 0 : endedAt - began,
        messages: captured,
        turnCount: captured.length,
        userTurnCount: captured.filter((message) => message.from?.isLocal === true).length,
        escalated: notice !== null,
        escalation: notice,
      };
    });
  }, [phase]);

  const [textOnly, setTextOnly] = useState(false);
  // Remembered so "Talk again" does not drag a caller who deliberately chose to
  // type back into a microphone request that already failed once.
  const lastStartOptions = useRef<{ microphone?: boolean } | undefined>(undefined);

  const start = useCallback(
    async (options?: { microphone?: boolean }) => {
      const withoutMic = options?.microphone === false;

      lastStartOptions.current = options;
      mic.clear();
      setTextOnly(withoutMic);

      try {
        // Starting without a microphone is how a caller whose mic is blocked can
        // still get health information by typing. Losing the voice channel should
        // not mean losing the service.
        await session.start(
          withoutMic ? { tracks: { microphone: { enabled: false } } } : undefined
        );
      } catch (error) {
        // A microphone problem is expected and explainable, so it is reported to
        // the caller rather than thrown. Anything else — a bad token, a dead
        // network — is not a microphone problem and must not be dressed up as one.
        if (!mic.report(error)) throw error;

        // The room connects before the microphone is published, so a blocked mic
        // leaves a live session the caller cannot speak on — with the agent on
        // the line talking to nobody, and every later start() a no-op because
        // the session is technically already connected. Closing it is what makes
        // "try again" and "continue by text" work at all.
        //
        // Only when a microphone was actually wanted. The text-only path still
        // surfaces a device error on some browsers even though it asked for no
        // microphone, and ending there would hang up a call that is working
        // exactly as intended.
        if (!withoutMic) {
          await session.end().catch(() => {
            // Already gone. Nothing to clean up.
          });
        }
      }
    },
    [session, mic]
  );

  const restart = useCallback(async () => {
    setSummary(null);
    setStartedAt(null);
    setElapsedMs(0);
    setHasBeenLive(false);
    clearEscalation();
    // Otherwise the previous call's record would bleed into the next slip.
    latest.current = { messages: [], escalation: null, startedAt: null };
    await start(lastStartOptions.current);
  }, [clearEscalation, start]);

  const value = useMemo<ConsultationContextValue>(
    () => ({
      phase,
      elapsedMs,
      escalation,
      summary,
      messages,
      agentUnavailable,
      agentFailureReasons: agent.failureReasons ?? [],
      isReconnecting,
      micFailure: mic.failure,
      clearMicFailure: mic.clear,
      textOnly,
      start,
      end: session.end,
      restart,
    }),
    [
      phase,
      elapsedMs,
      escalation,
      summary,
      messages,
      agentUnavailable,
      agent.failureReasons,
      isReconnecting,
      mic.failure,
      mic.clear,
      textOnly,
      start,
      session.end,
      restart,
    ]
  );

  return <ConsultationContext.Provider value={value}>{children}</ConsultationContext.Provider>;
}
