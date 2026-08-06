'use client';

import { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { type AgentState, type ReceivedMessage } from '@livekit/components-react';
import { cn } from '@/lib/shadcn/utils';

/**
 * The consultation record.
 *
 * Rather than chat bubbles, the transcript is laid out like case notes: a
 * mono-spaced timestamp and speaker in the left margin, the words themselves in
 * the body column, one ruled row per turn. It reads as a document you could
 * print and hand to a doctor — which is exactly what a transcript of a health
 * conversation should feel like.
 */

interface RecordTranscriptProps {
  messages: ReceivedMessage[];
  agentState?: AgentState;
  className?: string;
}

export function RecordTranscript({ messages, agentState, className }: RecordTranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // Follow the conversation, but only when the reader is already at the bottom —
  // otherwise scrolling back to re-read an answer would keep yanking them away.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 120) {
      endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages, agentState]);

  return (
    <div
      ref={scrollRef}
      className={cn('overflow-y-auto [scrollbar-width:thin]', className)}
      aria-live="polite"
      aria-label="Conversation record"
    >
      {messages.length === 0 && (
        <p className="text-muted-foreground py-8 text-center text-sm">
          Aapki baat yahan likhi jayegi. Your conversation will appear here.
        </p>
      )}

      <div className="divide-rule divide-y">
        <AnimatePresence initial={false}>
          {messages.map(({ id, timestamp, from, message }) => {
            const isUser = from?.isLocal === true;
            const time = new Date(timestamp).toLocaleTimeString('en-IN', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
              hour12: false,
            });

            return (
              <motion.article
                key={id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22, ease: 'easeOut' }}
                className="grid grid-cols-1 gap-x-4 gap-y-1 py-3 sm:grid-cols-[7.5rem_1fr]"
              >
                <div className="flex items-baseline gap-2 sm:flex-col sm:gap-0.5">
                  <span
                    className={cn('field-label', isUser ? 'text-muted-foreground' : 'text-primary')}
                  >
                    {isUser ? 'Aap · You' : 'Sathi'}
                  </span>
                  <time className="text-muted-foreground/70 font-mono text-[0.625rem] tabular-nums">
                    {time}
                  </time>
                </div>

                <p
                  className={cn(
                    'text-[0.9375rem] leading-relaxed text-pretty',
                    isUser ? 'text-foreground/75' : 'text-foreground'
                  )}
                >
                  {message}
                </p>
              </motion.article>
            );
          })}
        </AnimatePresence>
      </div>

      {agentState === 'thinking' && (
        <div className="text-muted-foreground flex items-center gap-2 py-3">
          <span className="field-label">Sathi</span>
          <span className="flex gap-1" aria-label="Thinking">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="bg-primary/60 size-1.5 rounded-full"
                animate={{ opacity: [0.25, 1, 0.25] }}
                transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.18 }}
              />
            ))}
          </span>
        </div>
      )}

      <div ref={endRef} />
    </div>
  );
}
