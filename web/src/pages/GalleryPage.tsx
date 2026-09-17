import { useEffect, useState } from 'react';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';
import { Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { Submission } from '../types';

export function GalleryPage() {
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [items, setItems] = useState<Submission[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQ(q), 300);
    return () => window.clearTimeout(id);
  }, [q]);

  useEffect(() => {
    setItems(null);
    setError(null);
    const params = debouncedQ ? `?q=${encodeURIComponent(debouncedQ)}` : '';
    api
      .get<Submission[]>(`/api/gallery${params}`)
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load the gallery.'));
  }, [debouncedQ, retryToken]);

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-section md:px-6">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <h1 className="text-h1 text-ink-900">Gallery</h1>
        <Input label="Search" placeholder="Search submissions" value={q} onChange={(e) => setQ(e.target.value)} className="sm:w-72" />
      </div>

      {items === null && !error && <SkeletonRows rows={5} cols={3} />}
      {error && <ErrorState description={error} onRetry={() => setRetryToken((v) => v + 1)} />}
      {items && items.length === 0 && debouncedQ === '' && (
        <EmptyState title="No submissions yet" description="Be the first to submit - your draft saves as you type." />
      )}
      {items && items.length === 0 && debouncedQ !== '' && (
        <EmptyState title="No matches" description={`Nothing matches "${debouncedQ}". Try a different search.`} />
      )}
      {items && items.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {items.map((s) => (
            <Card key={s.id} title={s.title} meta={s.track}>
              <p className="line-clamp-4 text-body text-ink-600">{s.description}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
