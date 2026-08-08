'use client';

import { type Speaker } from '@/components/sehat/ecg-visualizer';
import { cn } from '@/lib/shadcn/utils';

/**
 * Says in words who currently has the floor.
 *
 * The ECG trace and its colour already carry this, but Day 3 asks for it to be
 * unmistakable, and words survive colour blindness, a dim phone screen in
 * sunlight, and a caller who has never seen a waveform before.
 */

interface SpeakerCaptionProps {
  speaker: Speaker;
  /** Shown when neither party is speaking — usually the agent's state label. */
  idleLabel: string;
  className?: string;
}

export function SpeakerCaption({ speaker, idleLabel, className }: SpeakerCaptionProps) {
  const copy =
    speaker === 'user'
      ? { hindi: 'Aap bol rahe hain', english: 'Listening to you', tone: 'user' as const }
      : speaker === 'agent'
        ? { hindi: 'Sathi bol rahi hain', english: 'Sathi is speaking', tone: 'agent' as const }
        : { hindi: idleLabel, english: '', tone: 'idle' as const };

  return (
    <p
      aria-live="polite"
      className={cn('flex items-center justify-center gap-2 text-center', className)}
    >
      <span
        className={cn(
          'size-1.5 shrink-0 rounded-full',
          copy.tone === 'user' && 'bg-marigold animate-pulse',
          copy.tone === 'agent' && 'bg-primary animate-pulse',
          copy.tone === 'idle' && 'bg-muted-foreground/40'
        )}
      />
      <span
        className={cn(
          'text-sm leading-none font-medium',
          copy.tone === 'idle' ? 'text-muted-foreground' : 'text-foreground'
        )}
      >
        {copy.hindi}
      </span>
      {copy.english && <span className="field-label hidden sm:inline">· {copy.english}</span>}
    </p>
  );
}
