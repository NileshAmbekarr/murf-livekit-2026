'use client';

import { useState } from 'react';
import { ConnectionQuality } from 'livekit-client';
import {
  useAgent,
  useConnectionQualityIndicator,
  useIsSpeaking,
  useLocalParticipant,
  useSessionContext,
  useVoiceAssistant,
} from '@livekit/components-react';
import {
  AgentControlBar,
  type AgentControlBarControls,
} from '@/components/agents-ui/agent-control-bar';
import { formatElapsed, statusLabel } from '@/components/sehat/agent-status';
import { useConsultation } from '@/components/sehat/consultation-provider';
import { EcgVisualizer, type Speaker } from '@/components/sehat/ecg-visualizer';
import { EmergencyBanner } from '@/components/sehat/emergency-banner';
import { FacilityCard } from '@/components/sehat/facility-card';
import { MicDeniedNotice } from '@/components/sehat/mic-denied-notice';
import { RecordTranscript } from '@/components/sehat/record-transcript';
import { SpeakerCaption } from '@/components/sehat/speaker-caption';
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

/**
 * Signal strength, as a monitor field.
 *
 * This agent is built for connections that drop. A caller who can see the link is
 * weak understands why an answer is slow, instead of concluding the service is
 * broken and hanging up.
 */
function SignalReadout() {
  const { localParticipant } = useLocalParticipant();
  const { quality } = useConnectionQualityIndicator({ participant: localParticipant });

  if (quality === ConnectionQuality.Excellent || quality === ConnectionQuality.Good) {
    return null;
  }

  const weak = quality === ConnectionQuality.Poor || quality === ConnectionQuality.Lost;
  if (!weak) return null;

  return (
    <span className="text-marigold field-label" role="status">
      Network kamzor · Weak network
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
  const { state: agentState } = useAgent();
  const { audioTrack } = useVoiceAssistant();
  const { localParticipant } = useLocalParticipant();
  const {
    elapsedMs,
    escalation,
    facilities,
    messages,
    isReconnecting,
    micFailure,
    clearMicFailure,
    textOnly,
    end,
  } = useConsultation();
  // A caller who chose to type has nothing to say out loud, so the chat panel
  // starts open rather than making them hunt for it.
  const [chatOpen, setChatOpen] = useState(textOnly);

  const controls: AgentControlBarControls = {
    leave: true,
    microphone: true,
    chat: supportsChatInput,
    camera: supportsVideoInput,
    screenShare: supportsScreenShare,
  };

  // Who has the floor. The agent speaking wins, because its audio is what the
  // caller is hearing; otherwise the caller's own mic decides.
  //
  // `useIsSpeaking` rather than `localParticipant.isSpeaking`: the participant
  // object is a stable reference that mutates in place, so reading the property
  // directly would render once and then go stale — the caller's caption would
  // never light up.
  const callerIsSpeaking = useIsSpeaking(localParticipant);
  const speaker: Speaker = agentState === 'speaking' ? 'agent' : callerIsSpeaking ? 'user' : null;

  const micTrack = session.isConnected ? session.local.microphoneTrack : undefined;
  const idleLabel = statusLabel(agentState).hindi;

  return (
    <div ref={ref} className={cn('flex w-full justify-center px-3 py-4 md:px-4', className)}>
      <section className="register-card flex h-[calc(100svh-5.5rem)] w-full max-w-2xl flex-col rounded-sm p-4 md:p-6">
        {/* Record head */}
        <header className="border-rule-strong flex shrink-0 items-center justify-between gap-2 border-b pb-3">
          <div className="flex items-baseline gap-3">
            <span className="text-primary font-serif text-lg leading-none font-semibold">
              Consultation
            </span>
            <span className="text-muted-foreground font-mono text-[0.625rem] tabular-nums">
              {formatElapsed(elapsedMs)}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <SignalReadout />
            <StatusReadout />
          </div>
        </header>

        {/* An escalation stays on screen for the rest of the call. */}
        {escalation && <EmergencyBanner notice={escalation} className="mt-4 shrink-0" />}

        {/* Below the emergency banner, never above it: if both are on screen the
            ambulance number is the one that must be read first. */}
        {facilities && <FacilityCard notice={facilities} className="mt-4 shrink-0" />}

        {/* A dropped link must not read as a hang-up. */}
        {isReconnecting && (
          <p
            role="status"
            className="border-marigold/50 bg-marigold/5 text-foreground/80 mt-4 shrink-0 rounded-sm border-l-2 p-2.5 text-sm leading-snug"
          >
            Dobara jud rahe hain… ek pal rukiye. Reconnecting — please hold on.
          </p>
        )}

        {micFailure && <MicDeniedNotice kind={micFailure} onRetry={clearMicFailure} />}

        {/* Monitor strip */}
        <div className="border-rule bg-background mt-4 h-20 shrink-0 overflow-hidden rounded-sm border md:h-24">
          <EcgVisualizer
            state={agentState}
            audioTrack={audioTrack}
            userAudioTrack={micTrack}
            speaker={speaker}
            lineWidth={2}
          />
        </div>

        <SpeakerCaption speaker={speaker} idleLabel={idleLabel} className="mt-3 shrink-0" />

        {/* The record itself */}
        <RecordTranscript
          messages={messages}
          agentState={agentState}
          className="mt-3 min-h-0 flex-1 pr-1"
        />

        {/* Controls */}
        <div className="mt-3 shrink-0">
          <AgentControlBar
            variant="outline"
            controls={controls}
            isChatOpen={chatOpen}
            isConnected={session.isConnected}
            onDisconnect={end}
            onIsChatOpenChange={setChatOpen}
            className="rounded-sm"
          />
          <p className="text-muted-foreground mt-2 text-center text-[0.6875rem] leading-snug">
            Not a doctor — no diagnosis, no prescriptions. Emergency:{' '}
            <a href="tel:108" className="text-sindoor font-semibold underline">
              108
            </a>{' '}
            ·{' '}
            <a href="tel:112" className="text-sindoor font-semibold underline">
              112
            </a>
          </p>
        </div>
      </section>
    </div>
  );
};
