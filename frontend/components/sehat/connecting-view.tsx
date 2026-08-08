'use client';

import { ConnectionState } from 'livekit-client';
import { useAgent, useSessionContext } from '@livekit/components-react';
import { CheckIcon, CircleNotchIcon, WarningCircleIcon } from '@phosphor-icons/react/dist/ssr';
import { useConsultation } from '@/components/sehat/consultation-provider';
import { EcgVisualizer } from '@/components/sehat/ecg-visualizer';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

/**
 * The waiting room.
 *
 * This state did not exist before: the interface switched on `isConnected`, so
 * pressing start left the caller looking at an unchanged intake card. In testing,
 * a caller waited fourteen seconds in silence and hung up one second before the
 * agent came alive.
 *
 * So this view does two things. It says in words that the caller should wait —
 * Day 3 asks for that explicitly — and it shows real progress rather than a
 * spinner, so a slow connect looks like progress instead of a hang. The ECG runs
 * at the resting `connecting` rhythm and picks up once the agent arrives: a
 * flatline becoming a pulse.
 */

type StepState = 'done' | 'active' | 'waiting';

function Step({ label, hindi, state }: { label: string; hindi: string; state: StepState }) {
  return (
    <li className="flex items-center gap-3">
      <span
        className={cn(
          'flex size-5 shrink-0 items-center justify-center rounded-full border',
          state === 'done' && 'border-primary bg-primary text-primary-foreground',
          state === 'active' && 'border-marigold text-marigold',
          state === 'waiting' && 'border-rule text-muted-foreground/40'
        )}
      >
        {state === 'done' && <CheckIcon weight="bold" className="size-3" />}
        {state === 'active' && <CircleNotchIcon weight="bold" className="size-3 animate-spin" />}
      </span>

      <span className="flex flex-1 items-baseline justify-between gap-2">
        <span
          className={cn(
            'text-sm leading-snug',
            state === 'waiting' ? 'text-muted-foreground/60' : 'text-foreground'
          )}
        >
          {hindi}
        </span>
        <span className="field-label shrink-0">{label}</span>
      </span>
    </li>
  );
}

export const ConnectingView = ({ ref, className }: React.ComponentProps<'div'>) => {
  const session = useSessionContext();
  const agent = useAgent();
  const { agentUnavailable, agentFailureReasons, end, restart } = useConsultation();

  const roomReady = session.connectionState === ConnectionState.Connected;

  return (
    <div ref={ref} className={cn('flex w-full justify-center px-4 py-6', className)}>
      <section className="register-card w-full max-w-xl rounded-sm p-6 md:p-8">
        <div className="border-rule-strong flex items-baseline justify-between border-b pb-3">
          <span className="field-label">Health Companion</span>
          <span className="field-label">{agentUnavailable ? 'Not connected' : 'Connecting'}</span>
        </div>

        {agentUnavailable ? (
          <>
            <h1 className="text-primary mt-5 font-serif text-3xl leading-tight font-semibold tracking-tight md:text-4xl">
              Sathi se baat nahin ho payi
            </h1>
            <p className="text-foreground/80 mt-3 text-base leading-relaxed">
              Sehat Sathi abhi available nahin hai. Thodi der baad dobara koshish kijiye.
            </p>
            <p className="text-foreground/70 mt-2 text-sm leading-relaxed">
              Sehat Sathi couldn&apos;t be reached just now. This is usually temporary — please try
              again in a moment.
            </p>

            {agentFailureReasons.length > 0 && (
              <ul className="text-muted-foreground mt-3 space-y-1 font-mono text-[0.6875rem]">
                {agentFailureReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}

            {/* An emergency cannot wait for a voice agent to come back up. */}
            <div className="border-sindoor/40 bg-sindoor/5 mt-6 rounded-sm border-l-2 p-3">
              <p className="text-foreground/80 text-sm leading-relaxed">
                Agar yeh emergency hai to intezaar na kijiye — <strong>108</strong> par ambulance ke
                liye call kijiye, ya <strong>112</strong> par.
              </p>
            </div>

            <div className="mt-6 flex flex-col gap-2 sm:flex-row">
              <Button
                size="lg"
                onClick={() => void restart()}
                className="h-12 flex-1 rounded-sm font-mono text-xs font-semibold tracking-[0.14em] uppercase"
              >
                Dobara koshish karein
              </Button>
              <Button
                size="lg"
                variant="outline"
                onClick={() => void end()}
                className="h-12 flex-1 rounded-sm font-mono text-xs font-semibold tracking-[0.14em] uppercase"
              >
                Band karein
              </Button>
            </div>
          </>
        ) : (
          <>
            <h1 className="text-primary mt-5 font-serif text-3xl leading-tight font-semibold tracking-tight md:text-4xl">
              Jud rahe hain…
            </h1>
            <p className="text-foreground/80 mt-3 text-base leading-relaxed">
              Ek pal rukiye. Sathi abhi line par aa rahi hain.
            </p>
            <p className="text-foreground/70 mt-1 text-sm leading-relaxed">
              Please wait a moment — Sathi is joining the call.
            </p>

            <div className="border-rule bg-background mt-6 h-20 overflow-hidden rounded-sm border md:h-24">
              <EcgVisualizer state={roomReady ? 'listening' : 'connecting'} lineWidth={2} />
            </div>

            <ul className="mt-6 space-y-3">
              <Step hindi="Line jud gayi" label="Connected" state={roomReady ? 'done' : 'active'} />
              <Step
                hindi="Sathi line par aa rahi hain"
                label="Agent joining"
                state={!roomReady ? 'waiting' : agent.canListen ? 'done' : 'active'}
              />
            </ul>

            <Button
              variant="outline"
              onClick={() => void end()}
              className="mt-7 h-11 w-full rounded-sm font-mono text-xs font-semibold tracking-[0.14em] uppercase"
            >
              Radd karein · Cancel
            </Button>

            <p className="text-muted-foreground mt-4 flex items-start gap-2 text-[0.6875rem] leading-snug">
              <WarningCircleIcon weight="bold" className="mt-0.5 size-3.5 shrink-0" />
              <span>
                Dheemi internet par thoda samay lag sakta hai. On a slow connection this can take a
                few seconds.
              </span>
            </p>
          </>
        )}
      </section>
    </div>
  );
};
