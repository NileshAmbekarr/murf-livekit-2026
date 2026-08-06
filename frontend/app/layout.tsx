import { Fraunces, IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Devanagari } from 'next/font/google';
import { headers } from 'next/headers';
import { ThemeProvider } from '@/components/app/theme-provider';
import { ThemeToggle } from '@/components/app/theme-toggle';
import { cn } from '@/lib/shadcn/utils';
import { getAppConfig, getStyles } from '@/lib/utils';
import '@/styles/globals.css';

// Fraunces carries the "printed form" character in headings.
const fraunces = Fraunces({
  variable: '--font-fraunces',
  subsets: ['latin'],
  display: 'swap',
  axes: ['SOFT', 'WONK', 'opsz'],
});

const plexSans = IBM_Plex_Sans({
  variable: '--font-plex-sans',
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
});

// Loaded separately so Hindi replies from the agent render properly rather
// than falling back to a system font mid-transcript.
const plexDevanagari = IBM_Plex_Sans_Devanagari({
  variable: '--font-plex-devanagari',
  subsets: ['devanagari', 'latin'],
  weight: ['400', '500', '600'],
  display: 'swap',
});

const plexMono = IBM_Plex_Mono({
  variable: '--font-plex-mono',
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  display: 'swap',
});

interface RootLayoutProps {
  children: React.ReactNode;
}

export default async function RootLayout({ children }: RootLayoutProps) {
  const hdrs = await headers();
  const appConfig = await getAppConfig(hdrs);
  const styles = getStyles(appConfig);
  const { pageTitle, pageDescription } = appConfig;

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        fraunces.variable,
        plexSans.variable,
        plexDevanagari.variable,
        plexMono.variable,
        'scroll-smooth font-sans antialiased'
      )}
    >
      <head>
        {styles && <style>{styles}</style>}
        <title>{pageTitle}</title>
        <meta name="description" content={pageDescription} />
      </head>
      <body className="bg-background overflow-x-hidden">
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          {/* Register masthead — the printed header at the top of the form. */}
          <header className="border-rule-strong bg-background/85 fixed inset-x-0 top-0 z-50 flex h-11 items-center justify-between border-b px-4 backdrop-blur-sm md:px-6">
            <div className="flex items-baseline gap-2">
              <span className="text-primary font-serif text-sm font-semibold tracking-tight">
                Sehat Sathi
              </span>
              <span className="field-label hidden sm:inline">Health Access</span>
            </div>

            <div className="flex items-center gap-3">
              <span className="field-label hidden md:inline">
                Voice by{' '}
                <a
                  target="_blank"
                  rel="noopener noreferrer"
                  href="https://murf.ai/api/docs"
                  className="text-primary underline underline-offset-2"
                >
                  Murf Falcon
                </a>
              </span>
              <ThemeToggle className="size-7" />
            </div>
          </header>

          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
