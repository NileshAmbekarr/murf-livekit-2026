'use client';

import { WarningIcon } from '@phosphor-icons/react/dist/ssr';
import { type EscalationNotice } from '@/hooks/useEscalationSignal';
import { cn } from '@/lib/shadcn/utils';

/**
 * Shown when the agent escalates to emergency care.
 *
 * The caller is being told an ambulance number out loud at this moment. Asking
 * someone frightened to hold four digits in their head and then dial them is a
 * poor design; here the number is a link, so on a phone it is one tap.
 *
 * The numbers come from the signal the backend publishes, which reads them from
 * the same constants the spoken script uses. Nothing here is hardcoded, so the
 * screen cannot contradict the voice.
 *
 * This is the one place in the interface allowed to use sindoor.
 */

interface EmergencyBannerProps {
  notice: EscalationNotice;
  className?: string;
}

export function EmergencyBanner({ notice, className }: EmergencyBannerProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn('border-sindoor bg-sindoor/10 rounded-sm border-l-4 p-3', className)}
    >
      <div className="flex items-center gap-2">
        <WarningIcon weight="fill" className="text-sindoor size-4 shrink-0" />
        <span className="field-label text-sindoor">Emergency · आपातकाल</span>
      </div>

      <p className="text-foreground mt-2 text-sm leading-snug font-medium">
        Turant ambulance bulaiye. Call an ambulance now.
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        <EmergencyNumber number={notice.ambulance} label="Ambulance" />
        <EmergencyNumber number={notice.emergency} label="Emergency" />
        {notice.maternal && <EmergencyNumber number="102" label="Mother & baby" />}
      </div>
    </div>
  );
}

function EmergencyNumber({ number, label }: { number: string; label: string }) {
  return (
    <a
      href={`tel:${number}`}
      // min-h-11 keeps this a comfortable tap target on a phone, which is where
      // it matters most.
      className="bg-sindoor text-card flex min-h-11 flex-1 items-center justify-center gap-2 rounded-sm px-4 py-2 transition-opacity hover:opacity-90"
    >
      <span className="font-serif text-xl leading-none font-semibold tabular-nums">{number}</span>
      <span className="font-mono text-[0.625rem] tracking-[0.12em] uppercase opacity-90">
        {label}
      </span>
    </a>
  );
}
