'use client';

import { MicrophoneSlashIcon } from '@phosphor-icons/react/dist/ssr';
import { Button } from '@/components/ui/button';
import { type MicFailureKind } from '@/hooks/useMicPermission';

/**
 * What the caller sees when the microphone is unavailable.
 *
 * A card rather than a toast: a toast dismisses itself after a few seconds, and
 * this is a blocking condition the caller has to act on. Each cause gets its own
 * wording, because "allow the microphone" is useless advice to someone whose
 * headset is unplugged or whose microphone is busy in another call.
 *
 * Marigold, not sindoor. A blocked microphone is a problem, not an emergency —
 * and sindoor only keeps meaning "emergency" if it is never spent on anything
 * else.
 */

interface Copy {
  hindi: string;
  english: string;
  steps: string[];
}

const COPY: Record<MicFailureKind, Copy> = {
  denied: {
    hindi: 'Microphone ki permission nahin mili.',
    english: "Your browser blocked the microphone, so Sehat Sathi can't hear you.",
    steps: [
      'Address bar mein lock ya microphone icon par click kijiye.',
      'Microphone ko "Allow" kijiye, phir page refresh kijiye.',
    ],
  },
  notFound: {
    hindi: 'Koi microphone nahin mila.',
    english: "No microphone is connected, so there's nothing to listen with.",
    steps: [
      'Headset ya earphone theek se lagaya hai, yeh dekh lijiye.',
      'Phir "Dobara koshish karein" par click kijiye.',
    ],
  },
  inUse: {
    hindi: 'Microphone koi doosri app use kar rahi hai.',
    english: 'Another app is already using the microphone.',
    steps: [
      'WhatsApp, Zoom ya Meet jaisi call app band kar dijiye.',
      'Phir "Dobara koshish karein" par click kijiye.',
    ],
  },
};

interface MicDeniedNoticeProps {
  kind: MicFailureKind;
  onRetry: () => void;
  /** Shown only for a blocked microphone, where typing is still possible. */
  onContinueByText?: () => void;
}

export function MicDeniedNotice({ kind, onRetry, onContinueByText }: MicDeniedNoticeProps) {
  const copy = COPY[kind];

  return (
    <div role="alert" className="border-marigold/50 bg-marigold/5 mt-6 rounded-sm border-l-2 p-4">
      <div className="flex items-center gap-2">
        <MicrophoneSlashIcon weight="bold" className="text-marigold size-4 shrink-0" />
        <span className="field-label text-foreground">Microphone</span>
      </div>

      <p className="text-foreground mt-2 text-sm leading-relaxed font-medium">{copy.hindi}</p>
      <p className="text-foreground/70 mt-1 text-sm leading-relaxed">{copy.english}</p>

      <ol className="text-foreground/70 mt-3 space-y-1 text-sm leading-relaxed">
        {copy.steps.map((step, index) => (
          <li key={step} className="flex gap-2">
            <span className="text-marigold font-mono text-xs">{index + 1}.</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Button
          onClick={onRetry}
          className="h-11 flex-1 rounded-sm font-mono text-xs font-semibold tracking-[0.12em] uppercase"
        >
          Dobara koshish karein
        </Button>

        {/* A blocked microphone should not mean no health information at all —
            the agent already accepts typed input. */}
        {kind === 'denied' && onContinueByText && (
          <Button
            variant="outline"
            onClick={onContinueByText}
            className="h-11 flex-1 rounded-sm font-mono text-xs font-semibold tracking-[0.12em] uppercase"
          >
            Likh kar baat karein
          </Button>
        )}
      </div>
    </div>
  );
}
