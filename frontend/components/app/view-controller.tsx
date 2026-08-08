'use client';

import { AnimatePresence, motion } from 'motion/react';
import type { AppConfig } from '@/app-config';
import { ConnectingView } from '@/components/sehat/connecting-view';
import { useConsultation } from '@/components/sehat/consultation-provider';
import { EndedView } from '@/components/sehat/ended-view';
import { SessionView } from '@/components/sehat/session-view';
import { WelcomeView } from '@/components/sehat/welcome-view';

const MotionWelcomeView = motion.create(WelcomeView);
const MotionConnectingView = motion.create(ConnectingView);
const MotionSessionView = motion.create(SessionView);
const MotionEndedView = motion.create(EndedView);

const VIEW_MOTION_PROPS = {
  variants: {
    visible: { opacity: 1 },
    hidden: { opacity: 0 },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.4,
    ease: 'linear',
  },
};

interface ViewControllerProps {
  appConfig: AppConfig;
}

/**
 * Switches between the four stages of a consultation.
 *
 * This used to branch on `session.isConnected` alone, which meant the caller got
 * no feedback at all while connecting and was thrown back to a blank intake card
 * the moment they hung up. The phase comes from `ConsultationProvider` now.
 */
export function ViewController({ appConfig }: ViewControllerProps) {
  const { phase } = useConsultation();

  return (
    <AnimatePresence mode="wait">
      {phase === 'ready' && (
        <MotionWelcomeView
          key="welcome"
          {...VIEW_MOTION_PROPS}
          startButtonText={appConfig.startButtonText}
        />
      )}
      {phase === 'connecting' && <MotionConnectingView key="connecting" {...VIEW_MOTION_PROPS} />}
      {phase === 'live' && (
        <MotionSessionView
          key="session"
          {...VIEW_MOTION_PROPS}
          supportsChatInput={appConfig.supportsChatInput}
          supportsVideoInput={appConfig.supportsVideoInput}
          supportsScreenShare={appConfig.supportsScreenShare}
        />
      )}
      {phase === 'ended' && <MotionEndedView key="ended" {...VIEW_MOTION_PROPS} />}
    </AnimatePresence>
  );
}
