import { useState } from 'react';
import { Badge } from './ui';
import { cn } from '../lib/cn';
import type { QuestionAnswer, SubmissionImage } from '../types';

/**
 * The parts of the T1 field set that the project page and the judge's score
 * sheet both show: the image gallery, the tech tags and the answers to the
 * organizer's questions. Everything is rendered as text, never as HTML.
 */

/** One large image with a row of thumbnails to switch between them. */
export function ProjectGallery({ images, title }: { images: SubmissionImage[]; title: string }) {
  const [shown, setShown] = useState(0);
  if (images.length === 0) return null;
  const current = images[Math.min(shown, images.length - 1)];
  return (
    <div className="mb-4 flex flex-col gap-2">
      <div className="max-h-96 overflow-hidden rounded-md bg-surface-100">
        <img
          src={current.url}
          alt={`${title}, image ${shown + 1} of ${images.length}`}
          className="w-full object-cover"
        />
      </div>
      {images.length > 1 && (
        <ul className="flex flex-wrap gap-2" aria-label="More images">
          {images.map((image, index) => (
            <li key={image.id}>
              <button
                type="button"
                aria-label={`Show image ${index + 1} of ${images.length}`}
                aria-pressed={index === shown}
                onClick={() => setShown(index)}
                className={cn(
                  'h-14 w-20 overflow-hidden rounded-sm border-2 bg-surface-100',
                  'focus:outline-none focus:ring-[3px] focus:ring-brand-500/20',
                  index === shown ? 'border-brand-500' : 'border-transparent',
                )}
              >
                <img src={image.url} alt="" className="h-full w-full object-cover" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function TechTags({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null;
  return (
    <p className="flex flex-wrap gap-1.5" aria-label="Tech tags">
      {tags.map((t) => (
        <Badge key={t} status="neutral">
          {t}
        </Badge>
      ))}
    </p>
  );
}

export function Answers({ answers, heading }: { answers: QuestionAnswer[]; heading: string }) {
  if (answers.length === 0) return null;
  return (
    <section className="mt-4 flex flex-col gap-3" aria-label={heading}>
      <h3 className="text-label text-ink-800">{heading}</h3>
      <dl className="flex flex-col gap-3">
        {answers.map((a) => (
          <div key={a.question_id}>
            <dt className="text-meta text-ink-600">{a.prompt}</dt>
            <dd className="whitespace-pre-wrap text-body text-ink-800">{a.answer}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
