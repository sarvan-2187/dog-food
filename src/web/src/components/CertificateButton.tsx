import { useState } from 'react';
import { Button } from './ui';
import { ApiError, api } from '../lib/api';

/**
 * Downloads a submission's participation certificate (PLAN.md Phase 4 T4).
 *
 * The API decides who may have one and when - the team, or an organizer, and
 * only once results are revealed. We do not re-implement that gate here: the
 * 425 comes back with the organizer's own reveal date in the message, which is
 * more useful to read than anything the client could guess.
 */
export function CertificateButton({
  submissionId,
  onToast,
  size = 'md',
}: {
  submissionId: number;
  onToast: (message: string, ok: boolean) => void;
  size?: 'sm' | 'md';
}) {
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    try {
      await api.download(
        `/api/submissions/${submissionId}/certificate.pdf`,
        `submission-${submissionId}-certificate.pdf`,
      );
      onToast('Certificate downloaded.', true);
    } catch (err) {
      onToast(
        err instanceof ApiError ? err.message : 'Could not download the certificate. Please try again.',
        false,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button variant="secondary" size={size} loading={busy} loadingLabel="Preparing..." onClick={download}>
      Download certificate
    </Button>
  );
}
