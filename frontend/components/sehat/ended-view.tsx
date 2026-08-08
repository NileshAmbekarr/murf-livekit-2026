'use client';

import { useCallback } from 'react';
import { DownloadSimpleIcon } from '@phosphor-icons/react/dist/ssr';
import { formatElapsed } from '@/components/sehat/agent-status';
import {
  type ConsultationSummary,
  useConsultation,
} from '@/components/sehat/consultation-provider';
import { EmergencyBanner } from '@/components/sehat/emergency-banner';
import { MicDeniedNotice } from '@/components/sehat/mic-denied-notice';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

/**
 * The discharge slip — the *parchi*.
 *
 * Hanging up used to drop the caller back onto a blank intake card, throwing away
 * the transcript and offering no obvious way to start again. A paper health
 * register does not do that: it produces a slip you take home. So this closes the
 * consultation properly — what happened, how to get it in writing, and one clear
 * way to talk again.
 */

function SlipRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="record-field">
      <span className="field-label shrink-0">{label}</span>
      <span className="order-last shrink-0 font-mono text-sm font-medium tabular-nums">
        {value}
      </span>
    </div>
  );
}

/**
 * Build the printable record.
 *
 * The disclaimer and the emergency numbers go in the file itself, not just on
 * screen — the whole reason the transcript is styled as case notes is that
 * someone might hand it to a health worker, and it has to carry its own context
 * when it arrives without this page around it.
 */
function buildRecordText(summary: ConsultationSummary): string {
  const ended = new Date(summary.endedAt);
  const lines: string[] = [
    'SEHAT SATHI — CONSULTATION RECORD',
    '='.repeat(52),
    '',
    'Sehat Sathi is an information service, not a doctor.',
    'It does not diagnose and does not prescribe.',
    'In an emergency call 108 for an ambulance, or 112.',
    'For anything serious, see your ASHA worker or nearest PHC.',
    '',
    `Date      : ${ended.toLocaleDateString('en-IN')}`,
    `Ended     : ${ended.toLocaleTimeString('en-IN', { hour12: false })}`,
    `Duration  : ${formatElapsed(summary.durationMs)}`,
    `Turns     : ${summary.turnCount}`,
  ];

  if (summary.escalated) {
    lines.push('', 'AN EMERGENCY DANGER SIGN CAME UP DURING THIS CALL.');
    lines.push('The caller was told to seek emergency care immediately.');
  }

  lines.push('', '-'.repeat(52), 'TRANSCRIPT', '-'.repeat(52), '');

  if (summary.messages.length === 0) {
    lines.push('(no conversation was recorded)');
  }

  for (const { timestamp, from, message } of summary.messages) {
    const time = new Date(timestamp).toLocaleTimeString('en-IN', { hour12: false });
    lines.push(`[${time}] ${from?.isLocal === true ? 'Caller' : 'Sehat Sathi'}: ${message}`);
    lines.push('');
  }

  return lines.join('\n');
}

function downloadFilename(endedAt: number): string {
  const d = new Date(endedAt);
  const pad = (n: number) => String(n).padStart(2, '0');
  return [
    'sehat-sathi-record',
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    `${pad(d.getHours())}${pad(d.getMinutes())}`,
  ].join('-');
}

export const EndedView = ({ ref, className }: React.ComponentProps<'div'>) => {
  const { summary, restart, micFailure, clearMicFailure, start } = useConsultation();

  const handleDownload = useCallback(() => {
    if (!summary) return;

    const blob = new Blob([buildRecordText(summary)], {
      type: 'text/plain;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = `${downloadFilename(summary.endedAt)}.txt`;
    link.click();

    URL.revokeObjectURL(url);
  }, [summary]);

  const ended = summary ? new Date(summary.endedAt) : new Date();

  return (
    <div ref={ref} className={cn('flex w-full justify-center px-4 py-6', className)}>
      <section className="slip-card w-full max-w-xl rounded-sm p-6 md:p-8">
        <div className="border-rule-strong flex items-baseline justify-between border-b pb-3">
          <span className="field-label">Parchi · Consultation slip</span>
          <span className="field-label">No. 001</span>
        </div>

        <h1 className="text-primary mt-5 font-serif text-3xl leading-tight font-semibold tracking-tight md:text-4xl">
          Baat poori hui
        </h1>
        <p className="text-foreground/80 mt-3 text-base leading-relaxed">
          Apna dhyan rakhiye. Zaroorat ho to dobara baat kijiye.
        </p>
        <p className="text-foreground/70 mt-1 text-sm leading-relaxed">
          Take care. You can start another conversation whenever you need to.
        </p>

        <div className="mt-6 space-y-3">
          <SlipRow label="Duration" value={formatElapsed(summary?.durationMs ?? 0)} />
          <SlipRow label="Turns" value={String(summary?.turnCount ?? 0)} />
          <SlipRow label="Date" value={ended.toLocaleDateString('en-IN')} />
          <SlipRow
            label="Ended"
            value={ended.toLocaleTimeString('en-IN', {
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            })}
          />
        </div>

        {/* If a danger sign came up, the number stays on screen after the call.
            An emergency does not stop mattering because the line closed. */}
        {summary?.escalated && summary.escalation && (
          <EmergencyBanner notice={summary.escalation} className="mt-6" />
        )}

        {/* A call that died on the microphone would otherwise look like a call
            that simply ended, leaving the caller with nothing to act on. */}
        {micFailure && (
          <MicDeniedNotice
            kind={micFailure}
            onRetry={() => {
              clearMicFailure();
              void restart();
            }}
            onContinueByText={() => void start({ microphone: false })}
          />
        )}

        <Button
          size="lg"
          onClick={() => void restart()}
          className="mt-7 h-12 w-full rounded-sm font-mono text-xs font-semibold tracking-[0.14em] uppercase"
        >
          <span className="font-devanagari tracking-normal normal-case">फिर बात करें</span>
          <span aria-hidden="true" className="opacity-50">
            ·
          </span>
          Talk again
        </Button>

        <Button
          variant="outline"
          onClick={handleDownload}
          disabled={!summary || summary.messages.length === 0}
          className="mt-3 h-11 w-full rounded-sm font-mono text-xs font-semibold tracking-[0.12em] uppercase"
        >
          <DownloadSimpleIcon weight="bold" className="size-4" />
          Record download karein
        </Button>

        <div className="border-rule mt-6 border-t pt-4">
          <p className="text-foreground/70 text-sm leading-relaxed">
            Sehat Sathi is not a doctor and does not diagnose or prescribe. In an emergency call{' '}
            <a href="tel:108" className="text-sindoor font-semibold underline">
              108
            </a>{' '}
            for an ambulance, or{' '}
            <a href="tel:112" className="text-sindoor font-semibold underline">
              112
            </a>
            .
          </p>
        </div>
      </section>
    </div>
  );
};
