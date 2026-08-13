'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

interface AnalyticsData {
  total: number;
  successful: number;
  failed: number;
}

export default function DashboardPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  // Poll the API for live updates
  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const response = await fetch('/api/analytics');
        if (response.ok) {
          const json = await response.json();
          setData(json);
        }
      } catch (err) {
        console.error('Error fetching analytics:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchAnalytics();
    
    // Auto-refresh every 3 seconds for live updates
    const interval = setInterval(fetchAnalytics, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="min-h-screen paper-rules p-8 flex justify-center items-start pt-16">
      <div className="w-full max-w-2xl space-y-8">
        
        <header className="flex justify-between items-end">
          <div>
            <h1 className="font-serif text-4xl text-primary mb-2 tracking-tight">
              Call Analytics
            </h1>
            <p className="text-muted-foreground">
              Real-time outcomes from both browser and SIP calls.
            </p>
          </div>
          <Link href="/" className="text-sm font-mono uppercase tracking-widest hover:text-teal transition-colors">
            ← Back to Intake
          </Link>
        </header>

        {loading && !data ? (
          <div className="text-center p-12 text-muted-foreground animate-pulse">
            Loading ledger...
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            <div className="register-card p-6 flex flex-col justify-between h-40">
              <span className="field-label">Total Calls</span>
              <div className="text-6xl font-serif text-foreground">
                {data?.total ?? 0}
              </div>
            </div>

            <div className="register-card p-6 flex flex-col justify-between h-40">
              <span className="field-label">Successful</span>
              <div className="text-6xl font-serif text-teal">
                {data?.successful ?? 0}
              </div>
            </div>

            <div className="register-card p-6 flex flex-col justify-between h-40">
              <span className="field-label">Failed</span>
              <div className="text-6xl font-serif text-sindoor">
                {data?.failed ?? 0}
              </div>
            </div>
            
          </div>
        )}

        <div className="mt-12 text-xs text-muted-foreground text-center">
          <p>
            Success is defined as: "The caller receives safe guidance or an appropriate escalation."
            <br />
            Sensitive caller information is securely excluded from this dashboard.
          </p>
        </div>

      </div>
    </main>
  );
}
