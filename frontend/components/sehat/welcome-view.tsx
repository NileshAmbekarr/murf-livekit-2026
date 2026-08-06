'use client';

import { EcgVisualizer } from '@/components/sehat/ecg-visualizer';
import { Button } from '@/components/ui/button';

/**
 * The intake card.
 *
 * Modelled on the patient card handed out at a primary health centre: a ruled
 * form with the service's details filled into labelled fields, a resting ECG
 * strip, and one clear action. The emergency notice is part of the card rather
 * than fine print, because for this agent it is the single most important thing
 * on the page.
 */

interface RecordRowProps {
  label: string;
  value: string;
}

function RecordRow({ label, value }: RecordRowProps) {
  return (
    <div className="record-field">
      <span className="field-label shrink-0">{label}</span>
      <span className="order-last shrink-0 text-sm font-medium">{value}</span>
    </div>
  );
}

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: () => void;
}

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  return (
    <div ref={ref} className="flex w-full justify-center px-4 py-6">
      <section className="register-card w-full max-w-xl rounded-sm p-6 md:p-8">
        {/* Card head */}
        <div className="border-rule-strong flex items-baseline justify-between border-b pb-3">
          <span className="field-label">Health Companion</span>
          <span className="field-label">No. 001</span>
        </div>

        <h1 className="text-primary mt-5 font-serif text-4xl leading-none font-semibold tracking-tight md:text-5xl">
          Sehat Sathi
        </h1>
        <p className="text-foreground/80 mt-3 max-w-md text-base leading-relaxed">
          Apni sehat ke baare mein Hindi ya English mein baat kijiye — jaise aap ghar par karte
          hain. Talk about your health in Hindi or English, whichever comes naturally.
        </p>

        {/* Resting trace */}
        <div className="border-rule bg-background mt-6 h-24 overflow-hidden rounded-sm border">
          <EcgVisualizer state="listening" lineWidth={2} />
        </div>

        {/* Record fields */}
        <div className="mt-6 space-y-3">
          <RecordRow label="Voice" value="Anisha · Murf Falcon" />
          <RecordRow label="Languages" value="हिन्दी · English" />
          <RecordRow label="Helps with" value="Symptoms · Schemes · Helplines" />
        </div>

        <Button
          size="lg"
          onClick={onStartCall}
          className="mt-7 h-12 w-full rounded-sm font-mono text-xs font-semibold tracking-[0.14em] uppercase"
        >
          {startButtonText}
        </Button>

        {/* Emergency notice — sindoor red is used here and nowhere else. */}
        <div className="border-sindoor/40 bg-sindoor/5 mt-6 rounded-sm border-l-2 p-3">
          <p className="text-sindoor text-sm leading-relaxed font-medium">
            Sehat Sathi is not a doctor and does not diagnose or prescribe.
          </p>
          <p className="text-foreground/70 mt-1 text-sm leading-relaxed">
            In an emergency call <span className="text-sindoor font-semibold">108</span> for an
            ambulance, or <span className="text-sindoor font-semibold">112</span>. For anything
            serious, please see your ASHA worker or nearest PHC.
          </p>
        </div>
      </section>
    </div>
  );
};
