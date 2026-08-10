'use client';

import { MapPinIcon } from '@phosphor-icons/react/dist/ssr';
import { type FacilityNotice } from '@/hooks/useFacilitySignal';
import { cn } from '@/lib/shadcn/utils';

/**
 * Nearby health facilities, on screen while the agent speaks them.
 *
 * Teal, not sindoor. This is useful information, not an emergency, and the whole
 * point of reserving sindoor is that it keeps meaning one thing.
 *
 * Each row links with a `geo:` URI rather than `tel:` — the 108 banner can offer
 * a phone number because it is a constant, but Indian OpenStreetMap health data
 * almost never carries one (zero of the first sixty sampled). What a caller
 * actually needs is directions, and `geo:` opens the map app on a phone.
 *
 * The as-of date is shown, not hidden. Someone deciding whether to travel to a
 * clinic should know the listing is public map data of a certain age.
 */

interface FacilityCardProps {
  notice: FacilityNotice;
  className?: string;
}

function distanceLabel(km: number): string {
  return km < 1 ? '<1 km' : `${Math.round(km)} km`;
}

export function FacilityCard({ notice, className }: FacilityCardProps) {
  if (notice.items.length === 0) return null;

  return (
    <section
      aria-label="Nearby health facilities"
      className={cn('border-primary/40 bg-primary/5 rounded-sm border-l-2 p-3', className)}
    >
      <div className="flex items-center gap-2">
        <MapPinIcon weight="bold" className="text-primary size-4 shrink-0" />
        <span className="field-label text-foreground">Aas-paas · Nearby</span>
      </div>

      <ul className="divide-rule mt-2 divide-y">
        {notice.items.map((facility) => (
          <li key={`${facility.name}-${facility.lat}-${facility.lon}`}>
            <a
              href={`geo:${facility.lat},${facility.lon}?q=${encodeURIComponent(facility.name)}`}
              // min-h-11 keeps this a comfortable tap target on a phone.
              className="flex min-h-11 items-center justify-between gap-3 py-2 transition-opacity hover:opacity-80"
            >
              <span className="min-w-0">
                <span className="text-foreground block truncate text-sm font-medium">
                  {facility.name}
                </span>
                <span className="text-muted-foreground block truncate text-[0.6875rem]">
                  {facility.kind}
                  {facility.address ? ` · ${facility.address}` : ''}
                </span>
              </span>
              <span className="text-primary shrink-0 font-mono text-xs tabular-nums">
                {distanceLabel(facility.distanceKm)}
              </span>
            </a>
          </li>
        ))}
      </ul>

      <p className="text-muted-foreground mt-2 text-[0.6875rem] leading-snug">
        Public map data{notice.asOf ? `, ${notice.asOf}` : ''} — jaane se pehle phone kar lijiye.
        Distances are straight-line.
      </p>
    </section>
  );
}
