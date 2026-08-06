'use client';

import { useEffect, useState } from 'react';
import {
  useAgent,
  useSessionContext,
  useSessionMessages,
  useVoiceAssistant,
} from '@livekit/components-react';
import {
  AgentControlBar,
  type AgentControlBarControls,
} from '@/components/agents-ui/agent-control-bar';
import { formatElapsed, statusLabel } from '@/components/sehat/agent-status';
import { EcgVisualizer } from '@/components/sehat/ecg-visualizer';
import { RecordTranscript } from '@/components/sehat/record-transcript';
import { cn } from '@/lib/shadcn/utils';

/**
 * The live consultation view: a single register page, top to bottom —
 * monitor strip, then the record, then the controls.
 */

interface SessionViewProps {
  supportsChatInput?: boolean;
  supportsVideoInput?: boolean;
  supportsScreenShare?: boolean;
  className?: string;
}

function StatusReadout() {
  const { state } = useAgent();
  const label = statusLabel(state);

  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          'size-1.5 rounded-full',
          label.tone === 'active' ? 'bg-marigold animate-pulse' : 'bg-muted-foreground/50'
        )}
      />
      <span className="field-label text-foreground">{label.hindi}</span>
      <span className="field-label hidden sm:inline">· {label.english}</span>
    </div>
  );
}

function ElapsedTime() {
  const [startedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <span className="text-muted-foreground font-mono text-[0.625rem] tabular-nums">
      {formatElapsed(now - startedAt)}
    </span>
  );
}

export const SessionView = ({
  supportsChatInput = true,
  supportsVideoInput = false,
  supportsScreenShare = false,
  ref,
  className,
}: React.ComponentProps<'div'> & SessionViewProps) => {
  const session = useSessionContext();
  const { messages } = useSessionMessages(session);
  const { state: agentState } = useAgent();
  const { audioTrack } = useVoiceAssistant();
  const [chatOpen, setChatOpen] = useState(false);

  const controls: AgentControlBarControls = {
    leave: true,
    microphone: true,
    chat: supportsChatInput,
    camera: supportsVideoInput,
    screenShare: supportsScreenShare,
  };

  return (
    <div ref={ref} className={cn('flex w-full justify-center px-3 py-4 md:px-4', className)}>
      <section className="register-card flex h-[calc(100svh-5.5rem)] w-full max-w-2xl flex-col rounded-sm p-4 md:p-6">
        {/* Record head */}
        <header className="border-rule-strong flex shrink-0 items-center justify-between border-b pb-3">
          <div className="flex items-baseline gap-3">
            <span className="text-primary font-serif text-lg leading-none font-semibold">
              Consultation
            </span>
            <ElapsedTime />
          </div>
          <StatusReadout />
        </header>

        {/* Monitor strip */}
        <div className="border-rule bg-background mt-4 h-20 shrink-0 overflow-hidden rounded-sm border md:h-24">
          <EcgVisualizer state={agentState} audioTrack={audioTrack} lineWidth={2} />
        </div>

        {/* The record itself */}
        <RecordTranscript
          messages={messages}
          agentState={agentState}
          className="mt-4 min-h-0 flex-1 pr-1"
        />

        {/* Controls */}
        <div className="mt-3 shrink-0">
          <AgentControlBar
            variant="outline"
            controls={controls}
            isChatOpen={chatOpen}
            isConnected={session.isConnected}
            onDisconnect={session.end}
            onIsChatOpenChange={setChatOpen}
            className="rounded-sm"
          />
          <p className="text-muted-foreground mt-2 text-center text-[0.6875rem] leading-snug">
            Not a doctor — no diagnosis, no prescriptions. Emergency:{' '}
            <span className="text-sindoor font-semibold">108</span> ·{' '}
            <span className="text-sindoor font-semibold">112</span>
          </p>
        </div>
      </section>
    </div>
  );
};
