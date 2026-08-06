import { ImageResponse } from 'next/og';

/**
 * Social card for Sehat Sathi.
 *
 * Deliberately self-contained: no font downloads, no image files to resolve.
 * Everything is drawn from the design tokens in styles/globals.css, so the card
 * cannot break the build if an asset path changes.
 */

export const alt = 'Sehat Sathi — a Hindi and English health companion, powered by Murf Falcon';
export const size = { width: 1200, height: 628 };
export const contentType = 'image/png';

const PAPER = '#EEF1E4';
const INK = '#17231F';
const TEAL = '#1D4E49';
const MARIGOLD = '#E2951F';
const RULE = '#C9CDB8';

// One PQRST complex, repeated across the card.
const PULSE =
  'M0 60 H70 l10 -6 l8 14 l10 -52 l12 92 l10 -50 l8 12 h12 q10 0 14 -14 q4 -14 8 0 q4 14 14 14 H240';

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: size.width,
          height: size.height,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          backgroundColor: PAPER,
          // Ruled paper.
          backgroundImage: `repeating-linear-gradient(to bottom, ${PAPER} 0px, ${PAPER} 39px, ${RULE} 39px, ${RULE} 40px)`,
          padding: 64,
          fontFamily: 'sans-serif',
        }}
      >
        {/* Masthead */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `2px solid ${TEAL}`,
            paddingBottom: 20,
          }}
        >
          <div
            style={{
              display: 'flex',
              fontSize: 20,
              letterSpacing: 4,
              color: TEAL,
              fontWeight: 600,
            }}
          >
            HEALTH ACCESS · #VOICEFORBHARAT
          </div>
          <div style={{ display: 'flex', fontSize: 20, letterSpacing: 2, color: '#5C6B62' }}>
            LiveKit Agents
          </div>
        </div>

        {/* Title block */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div
            style={{ display: 'flex', fontSize: 96, fontWeight: 700, color: INK, lineHeight: 1 }}
          >
            Sehat Sathi
          </div>
          <div style={{ display: 'flex', fontSize: 34, color: TEAL, lineHeight: 1.3 }}>
            A health companion that speaks the way you do.
          </div>
          <div style={{ display: 'flex', fontSize: 26, color: '#5C6B62', maxWidth: 820 }}>
            Hindi and English, mixed freely. Symptoms explained, schemes and helplines found, and a
            straight line to real care when it matters.
          </div>
        </div>

        {/* ECG strip */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <svg width={1072} height={120} viewBox="0 0 1072 120">
            <rect x="0" y="0" width="1072" height="120" fill="#F6F8EF" stroke={RULE} />
            {[0, 240, 480, 720, 960].map((offset) => (
              <g key={offset} transform={`translate(${offset}, 0)`}>
                <path
                  d={PULSE}
                  fill="none"
                  stroke={TEAL}
                  strokeWidth={4}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
            ))}
          </svg>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 24,
            }}
          >
            <div style={{ display: 'flex', color: '#5C6B62' }}>
              Voice by{' '}
              <span style={{ color: MARIGOLD, fontWeight: 700, marginLeft: 8 }}>Murf Falcon</span>
            </div>
            <div style={{ display: 'flex', color: '#5C6B62' }}>Emergency? Call 108</div>
          </div>
        </div>
      </div>
    ),
    size
  );
}
