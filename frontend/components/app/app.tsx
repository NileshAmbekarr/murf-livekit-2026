'use client';

import { useEffect, useMemo, useState } from 'react';
import { TokenSource } from 'livekit-client';
import { useSession } from '@livekit/components-react';
import { WarningIcon } from '@phosphor-icons/react/dist/ssr';
import type { AppConfig } from '@/app-config';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { ViewController } from '@/components/app/view-controller';
import { ConsultationProvider } from '@/components/sehat/consultation-provider';
import { Toaster } from '@/components/ui/sonner';
import { useAgentErrors } from '@/hooks/useAgentErrors';
import { useDebugMode } from '@/hooks/useDebug';
import { getCallerId } from '@/lib/caller-id';
import { getSandboxTokenSource } from '@/lib/utils';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

function AppSetup() {
  useDebugMode({ enabled: IN_DEVELOPMENT });
  useAgentErrors();

  return null;
}

interface AppProps {
  appConfig: AppConfig;
}

export function App({ appConfig }: AppProps) {
  const tokenSource = useMemo(() => {
    return typeof process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT === 'string'
      ? getSandboxTokenSource(appConfig)
      : TokenSource.endpoint('/api/token');
  }, [appConfig]);

  // Read once on mount: it touches localStorage, so it must not run during SSR,
  // and a changing value mid-session would re-issue the token.
  const [callerId, setCallerId] = useState<string | undefined>(undefined);
  useEffect(() => setCallerId(getCallerId()), []);

  const session = useSession(tokenSource, {
    ...(appConfig.agentName ? { agentName: appConfig.agentName } : {}),
    // Lets the agent recognise a returning caller. Undefined on a first visit or
    // where storage is blocked, in which case the token route falls back to a
    // throwaway identity and the agent treats them as new.
    ...(callerId ? { participantIdentity: callerId } : {}),
  });

  return (
    <AgentSessionProvider session={session}>
      <AppSetup />
      {/* ConsultationProvider owns the ready/connecting/live/ended phase that the
          views switch on, plus the elapsed clock, escalation latch and the
          end-of-call snapshot the discharge slip is built from. */}
      <ConsultationProvider>
        {/* paper-rules draws the ruled backdrop the register cards sit on;
            pt-11 clears the fixed masthead in app/layout.tsx. */}
        <main className="paper-rules flex min-h-svh items-center justify-center pt-11">
          <ViewController appConfig={appConfig} />
        </main>
      </ConsultationProvider>
      <StartAudioButton label="Start Audio" />
      <Toaster
        icons={{
          warning: <WarningIcon weight="bold" />,
        }}
        position="top-center"
        className="toaster group"
        style={
          {
            '--normal-bg': 'var(--popover)',
            '--normal-text': 'var(--popover-foreground)',
            '--normal-border': 'var(--border)',
          } as React.CSSProperties
        }
      />
    </AgentSessionProvider>
  );
}
