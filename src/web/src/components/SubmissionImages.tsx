import { useRef, useState } from 'react';
import { Badge, Button } from './ui';
import { ApiError, api } from '../lib/api';
import type { SubmissionImage } from '../types';

const MAX_IMAGES = 5;
const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

/**
 * A submission's image gallery (DOGFOOD T1): up to five pictures, in order,
 * the first being the thumbnail on gallery cards. Each change is saved on the
 * server straight away and the server's order is what's shown, so the list can
 * never drift from what the gallery will display.
 *
 * Moving is done with buttons rather than drag and drop, so it works the same
 * from a keyboard. The type and size checks here only save a round trip: the
 * server repeats them, and also checks the file's magic bytes.
 */
export function SubmissionImages({
  teamId,
  images,
  onChange,
}: {
  teamId: string;
  images: SubmissionImage[];
  onChange: (images: SubmissionImage[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = `/api/teams/${teamId}/submission/images`;

  async function run(label: string, action: () => Promise<SubmissionImage[]>) {
    setBusy(label);
    setError(null);
    try {
      onChange(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update your images.');
    } finally {
      setBusy(null);
    }
  }

  function add(file: File) {
    if (!ALLOWED_TYPES.includes(file.type)) {
      setError('Use PNG, JPEG, WebP, or GIF.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('Image must be under 5MB.');
      return;
    }
    run('add', () => api.upload<SubmissionImage[]>(base, file));
  }

  function move(index: number, by: -1 | 1) {
    const ids = images.map((i) => i.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    run(`move-${images[index].id}`, () => api.put<SubmissionImage[]>(`${base}/order`, { image_ids: ids }));
  }

  return (
    <div className="flex flex-col gap-3">
      {images.length > 0 && (
        <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-label="Project images, in order">
          {images.map((image, index) => (
            <li key={image.id} className="flex flex-col gap-2 rounded-md border border-border-subtle p-2">
              <div className="aspect-video overflow-hidden rounded-sm bg-surface-100">
                <img src={image.url} alt={`Image ${index + 1}`} className="h-full w-full object-cover" />
              </div>
              <span className="flex items-center justify-between gap-2">
                <span className="text-meta text-ink-600">Image {index + 1}</span>
                {index === 0 && <Badge status="info">Thumbnail</Badge>}
              </span>
              <span className="flex flex-wrap gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={index === 0 || busy !== null}
                  aria-label={`Move image ${index + 1} earlier`}
                  onClick={() => move(index, -1)}
                >
                  &larr;
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={index === images.length - 1 || busy !== null}
                  aria-label={`Move image ${index + 1} later`}
                  onClick={() => move(index, 1)}
                >
                  &rarr;
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={busy === `remove-${image.id}`}
                  loadingLabel="Removing..."
                  disabled={busy !== null && busy !== `remove-${image.id}`}
                  aria-label={`Remove image ${index + 1}`}
                  onClick={() => run(`remove-${image.id}`, () => api.del<SubmissionImage[]>(`${base}/${image.id}`))}
                >
                  Remove
                </Button>
              </span>
            </li>
          ))}
        </ol>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={ALLOWED_TYPES.join(',')}
        className="hidden"
        aria-label="Choose an image to add"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) add(file);
          e.target.value = ''; // lets the same file be re-picked after an error
        }}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          loading={busy === 'add'}
          loadingLabel="Uploading..."
          disabled={images.length >= MAX_IMAGES || (busy !== null && busy !== 'add')}
          onClick={() => inputRef.current?.click()}
        >
          Add image
        </Button>
        <span className="text-meta text-ink-500">
          {images.length} of {MAX_IMAGES}. The first is the thumbnail on gallery cards.
        </span>
      </div>
      {error && (
        <p role="alert" className="text-meta text-danger-fg">
          {error}
        </p>
      )}
    </div>
  );
}
