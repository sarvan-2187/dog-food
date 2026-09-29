import { useRef, useState } from 'react';
import { Badge, Button } from './ui';
import { ApiError, api } from '../lib/api';

const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

/**
 * One upload control shared by the submission screenshot field and the
 * profile avatar field (PLAN.md Phase 6 UX checklist) - only the endpoint,
 * label, and image shape differ between the two call sites.
 */
export function ImageUpload({
  uploadUrl,
  currentUrl,
  label,
  shape = 'rectangle',
  responseKey,
  onUploaded,
}: {
  uploadUrl: string;
  currentUrl: string | null;
  label: string;
  shape?: 'rectangle' | 'circle';
  responseKey: string;
  onUploaded: (url: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shown = preview ?? currentUrl;
  const frameClass = shape === 'circle' ? 'rounded-full' : 'rounded-md';

  async function onFileChosen(file: File) {
    setError(null);
    if (!ALLOWED_TYPES.includes(file.type)) {
      setError('Use PNG, JPEG, WebP, or GIF.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('Image must be under 5MB.');
      return;
    }
    const localPreview = URL.createObjectURL(file);
    setPreview(localPreview);
    setUploading(true);
    try {
      const body = await api.upload<Record<string, string>>(uploadUrl, file);
      onUploaded(body[responseKey]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not upload this image.');
      setPreview(null);
    } finally {
      setUploading(false);
      URL.revokeObjectURL(localPreview);
    }
  }

  return (
    <div className="flex items-center gap-4">
      <div
        className={`flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden border border-border-subtle bg-surface-100 ${frameClass}`}
      >
        {shown ? (
          <img src={shown} alt="" className="h-full w-full object-cover" />
        ) : (
          <span className="text-meta text-ink-500">No image</span>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED_TYPES.join(',')}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onFileChosen(file);
            e.target.value = ''; // lets the same file be re-picked after an error
          }}
        />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          loading={uploading}
          loadingLabel="Uploading..."
          onClick={() => inputRef.current?.click()}
        >
          {shown ? `Replace ${label}` : `Upload ${label}`}
        </Button>
        {error && (
          <p role="alert" className="text-meta text-danger-fg">
            {error}
          </p>
        )}
        {!error && !uploading && preview && <Badge status="success">Uploaded</Badge>}
      </div>
    </div>
  );
}
