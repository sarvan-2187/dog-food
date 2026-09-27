export type Role = 'participant' | 'judge' | 'organizer' | 'admin';

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
}

export interface EventRecord {
  id: number;
  slug: string;
  name: string;
  description: string;
  start_at: string;
  end_at: string;
  tracks: string[];
  created_by_id: number;
  created_at: string;
  voting_enabled: boolean;
  /** null means results were never hidden. */
  results_hidden_until: string | null;
}

export interface TeamMember {
  id: number;
  name: string;
  email: string;
}

export interface Team {
  id: number;
  event_id: number;
  name: string;
  invite_code: string;
  members: TeamMember[];
}

export type SubmissionStatus = 'draft' | 'submitted';

export interface Submission {
  id: number;
  team_id: number;
  event_id: number;
  title: string;
  description: string;
  track: string;
  status: SubmissionStatus;
  created_at: string;
  updated_at: string;
}

// --- Phase 2: judging ------------------------------------------------------

export interface Criterion {
  key: string;
  label: string;
  weight: number;
  max_score: number;
}

export interface Rubric {
  id: number;
  event_id: number;
  name: string;
  criteria: Criterion[];
  created_at: string;
  updated_at: string;
}

export interface Assignment {
  id: number;
  submission_id: number;
  judge_id: number;
  submission_title: string;
  scored: boolean;
}

export interface JudgeProgress {
  completed: number;
  total: number;
  pending: Assignment[];
  done: Assignment[];
}

export interface CoverageWarning {
  submission_id: number;
  submission_title: string;
  judges_short: number;
}

export interface AssignmentSummary {
  created: number;
  existing: number;
  judges_per_submission: number;
  coverage_warnings: CoverageWarning[];
  rubric_id: number | null;
}

export interface ScoringSheet {
  assignment_id: number;
  submission_id: number;
  submission_title: string;
  submission_description: string;
  submission_track: string;
  rubric_name: string;
  criteria: Criterion[];
  my_values: Record<string, number> | null;
  my_comment: string;
  my_raw_total: number | null;
}

export interface Score {
  id: number;
  assignment_id: number;
  submission_id: number;
  values: Record<string, number>;
  comment: string;
  raw_total: number;
}

export interface ResultRow {
  rank: number;
  submission_id: number;
  submission_title: string;
  team_name: string;
  judges: number;
  raw_mean: number;
  z_bar: number;
  display: number;
}


// --- Phase 3: community voting and comments --------------------------------

/**
 * `votes` is null while the event's results are hidden - the server withholds
 * the count from the payload rather than relying on the UI to hide it, so the
 * UI must handle its absence rather than treat it as zero.
 */
export interface GalleryItem {
  id: number;
  event_id: number;
  team_id: number;
  title: string;
  description: string;
  track: string;
  updated_at: string;
  comment_count: number;
  votes: number | null;
  voted_by_me: boolean;
}

export interface VoteResult {
  submission_id: number;
  voted: boolean;
  votes: number | null;
}

export interface CommentRecord {
  id: number;
  submission_id: number;
  author_name: string;
  body: string;
  created_at: string;
}

export interface PublicResultRow {
  rank: number;
  submission_id: number;
  submission_title: string;
  team_name: string;
  votes: number;
}
