'use client';

import { useEffect, useRef } from 'react';
import { useTheme } from 'next-themes';
import { LocalAudioTrack, RemoteAudioTrack } from 'livekit-client';
import {
  type AgentState,
  type TrackReference,
  type TrackReferenceOrPlaceholder,
  useTrackVolume,
} from '@livekit/components-react';
import { cn } from '@/lib/shadcn/utils';

/**
 * A scrolling ECG trace that doubles as the agent's voice visualizer.
 *
 * Why an ECG rather than the usual bars: this is a health-access agent, and a
 * cardiac trace is the one piece of medical iconography that reads instantly
 * across languages and literacy levels. It also happens to map cleanly onto
 * agent state — a resting rhythm while listening, a faster one while thinking,
 * and a trace whose amplitude is driven by the actual TTS audio while speaking.
 *
 * The trace is generated, not sampled: we synthesise a PQRST complex and
 * modulate its rate and amplitude. Real audio only drives amplitude and
 * baseline tremor, because a raw waveform doesn't look like a heartbeat.
 */

/** Samples held in the scrolling buffer. Higher = longer visible history. */
const BUFFER = 620;
/** Samples advanced per second — the "paper speed" of the trace. */
const PAPER_SPEED = 190;

interface RhythmSpec {
  /** Beats per minute of the synthesised complex. */
  bpm: number;
  /** Height of the R spike, as a fraction of half the canvas height. */
  amplitude: number;
  /** Random baseline movement between beats. */
  tremor: number;
  /** Trace opacity. */
  opacity: number;
}

const RHYTHMS: Record<string, RhythmSpec> = {
  disconnected: { bpm: 0, amplitude: 0, tremor: 0, opacity: 0.35 },
  initializing: { bpm: 48, amplitude: 0.18, tremor: 0.004, opacity: 0.5 },
  connecting: { bpm: 48, amplitude: 0.18, tremor: 0.004, opacity: 0.5 },
  listening: { bpm: 66, amplitude: 0.62, tremor: 0.006, opacity: 1 },
  thinking: { bpm: 104, amplitude: 0.34, tremor: 0.016, opacity: 0.85 },
  speaking: { bpm: 82, amplitude: 0.7, tremor: 0.01, opacity: 1 },
};

/**
 * One PQRST complex over a normalised beat phase `t` in [0, 1).
 *
 * P and T are gaussian bumps; the QRS complex is piecewise-linear so the R
 * spike stays genuinely sharp instead of being rounded off by a curve fit.
 * The segments are chosen to meet at their endpoints, so the trace is
 * continuous across the whole beat.
 */
function pqrst(t: number): number {
  const bump = (centre: number, width: number, height: number) =>
    height * Math.exp(-((t - centre) ** 2) / (2 * width * width));

  // P wave (atrial) and T wave (repolarisation).
  let y = bump(0.14, 0.018, 0.13) + bump(0.46, 0.035, 0.22);

  // QRS complex.
  if (t > 0.21 && t < 0.3) {
    const u = (t - 0.21) / 0.09;
    if (u < 0.22) {
      y += -0.18 * (u / 0.22); // Q: small dip
    } else if (u < 0.5) {
      y += -0.18 + 1.18 * ((u - 0.22) / 0.28); // R: the spike
    } else if (u < 0.75) {
      y += 1.0 - 1.42 * ((u - 0.5) / 0.25); // S: undershoot
    } else {
      y += -0.42 + 0.42 * ((u - 0.75) / 0.25); // return to baseline
    }
  }

  return y;
}

function readColor(el: HTMLElement, variable: string, fallback: string): string {
  const value = getComputedStyle(el).getPropertyValue(variable).trim();
  return value || fallback;
}

export interface EcgVisualizerProps {
  /** Current agent state; drives rate and amplitude. */
  state?: AgentState;
  /** Agent audio track; drives amplitude while speaking. */
  audioTrack?: LocalAudioTrack | RemoteAudioTrack | TrackReferenceOrPlaceholder;
  /** Render the ECG graph-paper grid behind the trace. */
  showGrid?: boolean;
  /** Stroke width of the trace in CSS pixels. */
  lineWidth?: number;
  className?: string;
}

export function EcgVisualizer({
  state = 'disconnected',
  audioTrack,
  showGrid = true,
  lineWidth = 2,
  className,
}: EcgVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  const volume = useTrackVolume(audioTrack as TrackReference, {
    fftSize: 256,
    smoothingTimeConstant: 0.6,
  });

  // Keep the latest values in refs so the animation loop never restarts —
  // restarting it would jump the trace.
  const stateRef = useRef(state);
  const volumeRef = useRef(volume);
  stateRef.current = state;
  volumeRef.current = volume;

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const samples = new Float32Array(BUFFER);
    let width = 0;
    let height = 0;
    let dpr = 1;

    const colors = {
      trace: readColor(container, '--teal', '#1d4e49'),
      grid: readColor(container, '--rule', '#c9cdb8'),
    };

    const resize = () => {
      const rect = container.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(rect.width, 1);
      height = Math.max(rect.height, 1);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let phase = 0; // beat phase, [0, 1)
    let carry = 0; // fractional samples not yet emitted
    let tremorSeed = 0;
    let last = performance.now();
    let frame = 0;

    const pushSample = (rhythm: RhythmSpec, amplitude: number) => {
      // Smoothed pseudo-noise for the baseline, so it wanders instead of buzzing.
      tremorSeed = tremorSeed * 0.82 + (Math.random() - 0.5) * 0.18;
      const beat = rhythm.bpm > 0 ? pqrst(phase) * amplitude : 0;
      const wander = tremorSeed * rhythm.tremor * 14;
      samples.copyWithin(0, 1);
      samples[BUFFER - 1] = beat + wander;
    };

    const drawGrid = () => {
      if (!showGrid) return;
      const fine = 9;
      const bold = fine * 5;
      ctx.save();
      ctx.strokeStyle = colors.grid;
      ctx.lineWidth = 1;

      ctx.globalAlpha = 0.28;
      ctx.beginPath();
      for (let x = width % fine; x < width; x += fine) {
        ctx.moveTo(Math.floor(x) + 0.5, 0);
        ctx.lineTo(Math.floor(x) + 0.5, height);
      }
      for (let y = height / 2 - Math.floor(height / 2 / fine) * fine; y < height; y += fine) {
        ctx.moveTo(0, Math.floor(y) + 0.5);
        ctx.lineTo(width, Math.floor(y) + 0.5);
      }
      ctx.stroke();

      ctx.globalAlpha = 0.55;
      ctx.beginPath();
      for (let x = width % bold; x < width; x += bold) {
        ctx.moveTo(Math.floor(x) + 0.5, 0);
        ctx.lineTo(Math.floor(x) + 0.5, height);
      }
      for (let y = height / 2 - Math.floor(height / 2 / bold) * bold; y < height; y += bold) {
        ctx.moveTo(0, Math.floor(y) + 0.5);
        ctx.lineTo(width, Math.floor(y) + 0.5);
      }
      ctx.stroke();
      ctx.restore();
    };

    const render = (rhythm: RhythmSpec) => {
      ctx.clearRect(0, 0, width, height);
      drawGrid();

      const mid = height / 2;
      const scale = height / 2 - lineWidth;
      const step = width / (BUFFER - 1);

      ctx.save();
      ctx.globalAlpha = rhythm.opacity;
      ctx.strokeStyle = colors.trace;
      ctx.lineWidth = lineWidth;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.beginPath();
      for (let i = 0; i < BUFFER; i++) {
        const x = i * step;
        const y = mid - samples[i] * scale;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // The leading edge, like the sweep dot on a bedside monitor.
      const headY = mid - samples[BUFFER - 1] * scale;
      ctx.fillStyle = colors.trace;
      ctx.beginPath();
      ctx.arc(width - 1, headY, lineWidth * 1.6, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = rhythm.opacity * 0.25;
      ctx.beginPath();
      ctx.arc(width - 1, headY, lineWidth * 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // Fade out the oldest samples so the trace emerges from the paper
      // rather than being clipped off at the left edge.
      const fade = ctx.createLinearGradient(0, 0, width * 0.22, 0);
      fade.addColorStop(0, 'rgba(0,0,0,1)');
      fade.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = fade;
      ctx.fillRect(0, 0, width * 0.22, height);
      ctx.restore();
    };

    const tick = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;

      const rhythm = RHYTHMS[stateRef.current] ?? RHYTHMS.listening;

      // While speaking, the caller should see the agent's actual voice energy.
      const speaking = stateRef.current === 'speaking';
      const amplitude = speaking
        ? rhythm.amplitude * (0.55 + 1.5 * Math.min(volumeRef.current, 1))
        : rhythm.amplitude;

      const advance = PAPER_SPEED * dt + carry;
      const whole = Math.floor(advance);
      carry = advance - whole;

      for (let i = 0; i < whole; i++) {
        if (rhythm.bpm > 0) {
          phase = (phase + rhythm.bpm / 60 / PAPER_SPEED) % 1;
        }
        pushSample(rhythm, amplitude);
      }

      render(rhythm);
      frame = requestAnimationFrame(tick);
    };

    if (reduceMotion) {
      // Draw a single static resting trace and stop.
      const rhythm = RHYTHMS.listening;
      for (let i = 0; i < BUFFER; i++) {
        phase = (phase + rhythm.bpm / 60 / PAPER_SPEED) % 1;
        pushSample(rhythm, rhythm.amplitude);
      }
      render({ ...rhythm, opacity: 0.9 });
    } else {
      frame = requestAnimationFrame(tick);
    }

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
    // resolvedTheme is a dependency so the trace re-reads its colours when the
    // user flips between light and dark.
  }, [showGrid, lineWidth, resolvedTheme]);

  return (
    <div
      ref={containerRef}
      className={cn('relative h-full w-full overflow-hidden', className)}
      role="img"
      aria-label={`Voice activity trace, agent is ${state}`}
    >
      <canvas ref={canvasRef} className="block" />
    </div>
  );
}
