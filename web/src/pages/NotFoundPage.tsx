import { Link } from 'react-router-dom';
import { EmptyState } from '../components/feedback';
import { Button } from '../components/ui';

/** No screen is a dead end (PLAN.md 4.4) - an unknown URL still offers a way out. */
export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-section">
      <EmptyState
        title="We could not find that page"
        description="The link may be out of date, or the event may have been removed."
        action={
          <Link to="/events">
            <Button variant="primary">Browse events</Button>
          </Link>
        }
      />
    </div>
  );
}
