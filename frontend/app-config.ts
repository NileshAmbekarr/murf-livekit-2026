export interface AppConfig {
  pageTitle: string;
  pageDescription: string;
  companyName: string;

  supportsChatInput: boolean;
  supportsVideoInput: boolean;
  supportsScreenShare: boolean;
  isPreConnectBufferEnabled: boolean;

  logo: string;
  startButtonText: string;
  accent?: string;
  logoDark?: string;
  accentDark?: string;

  /** Agent dispatch configuration — must match `agent_name` in backend/src/agent.py. */
  agentName?: string;

  /** LiveKit Cloud Sandbox configuration. */
  sandboxId?: string;
}

export const APP_CONFIG_DEFAULTS: AppConfig = {
  companyName: 'Sehat Sathi',
  pageTitle: 'Sehat Sathi — your health companion',
  pageDescription:
    'A Hindi and English voice companion for health access across India. Ask about symptoms, government health schemes and helplines. Powered by Murf Falcon TTS on LiveKit.',

  supportsChatInput: true,
  // A health helpline is a voice and text service — camera and screen share
  // would only add friction (and a privacy question) for the people it is for.
  supportsVideoInput: false,
  supportsScreenShare: false,
  isPreConnectBufferEnabled: true,

  logo: '/sehat-sathi-mark.svg',
  logoDark: '/sehat-sathi-mark-dark.svg',
  // Deep teal / lamplit teal — kept in step with --primary in styles/globals.css.
  accent: '#1D4E49',
  accentDark: '#5FB3A9',
  startButtonText: 'Baat shuru karein',

  // Explicit dispatch: the backend worker registers under this name.
  agentName: process.env.AGENT_NAME ?? 'sehat-sathi',

  sandboxId: undefined,
};
