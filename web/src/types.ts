export type Role = 'participant' | 'judge' | 'organizer' | 'admin';

export interface WebhookRecord {
  id: number;
  url: string;
  active: boolean;
  // 'blocked': the URL named or resolved to a private address (SSRF guard).
  last_status: 'never fired' | 'delivered' | 'failed' | 'blocked';
  created_at: string;
}

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  avatar_url: string | null;
  /** Proven by following an emailed link. Events can require it to vote. */
  email_verified?: boolean;
}

export interface PrizeEntry {
  rank: string;
  reward: string;
}

export interface EventRecord {
  id: number;
  slug: string;
  name: string;
  description: string;
  start_at: string;
  end_at: string;
  tracks: string[];
  /** Convention: { prizes: [{rank, reward}, ...] }. Empty object means none configured. */
  prize_config: { prizes?: PrizeEntry[] };
  max_team_size: number;
  created_by_id: number;
  created_at: string;
  voting_enabled: boolean;
  /** Who may vote: an account, a guest who confirmed an emailed link, or anyone with the link. */
  voting_access: 'authenticated' | 'email' | 'open';
  /** null means results were never hidden. */
  results_hidden_until: string | null;
  /** Soft judging deadline; null means none set. */
  judging_deadline?: string | null;
  /** Opt-in sybil defences for account voters (THREAT-MODEL entry 25). */
  voting_requires_verified?: boolean;
  voting_account_cutoff?: string | null;
  /** Organizer-supplied cover art; null falls back to a bundled photo (lib/event-cover.ts). */
  cover_image_url: string | null;
  /** PLAN.md 10.12 - drafts are only ever returned to organizers/admins. */
  status: 'draft' | 'published';
  /** PLAN.md 10.8 - plain text, rendered as text, never as HTML. */
  rules: string;
  /** Named rounds (Stage 1, Stage 2, ...) in start order. Informational. */
  stages: EventStage[];
  /** Organizer-defined questions teams answer on the submission form (DOGFOOD T1). */
  questions?: EventQuestion[];
  /** How its certificates look: a key of CERTIFICATE_DESIGNS. */
  certificate_template?: string;
}

export interface EventStage {
  name: string;
  description: string;
  starts_at: string;
  ends_at: string;
}

/** What a certificate certifies - GET /api/certificates/{serial}, public. */
export interface CertificateRecord {
  serial: string;
  event_name: string;
  event_slug: string;
  event_dates: string;
  team_name: string;
  members: string[];
  submission_title: string;
  rank: number | null;
  prizes: string[];
}

export interface ApiKeyRecord {
  id: number;
  name: string;
  hint: string;
  created_at: string;
  last_used_at: string | null;
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
  max_team_size: number;
  /** PLAN.md 10.9 - whoever created the team; may rename, remove, hand over. */
  captain_id: number | null;
  invite_code_expires_at: string | null;
}

export type SubmissionStatus = 'draft' | 'submitted';

/** One custom question. Short text answers, at most 1000 characters. */
export interface EventQuestion {
  id: string;
  prompt: string;
  required: boolean;
  /** Retired: off the form, the score sheet and the project page, answers kept. */
  hidden: boolean;
  /** Shown on the public project page; judges always see answers. */
  public: boolean;
}

export interface SubmissionImage {
  id: number;
  url: string;
}

export interface QuestionAnswer {
  question_id: string;
  prompt: string;
  answer: string;
}

export interface Submission {
  id: number;
  team_id: number;
  event_id: number;
  title: string;
  tagline: string;
  description: string;
  track: string;
  tech_tags: string[];
  status: SubmissionStatus;
  created_at: string;
  updated_at: string;
  /** The first gallery image, used as the thumbnail. */
  image_url: string | null;
  /** Up to five, in order. */
  images: SubmissionImage[];
  /** This team's answers, keyed by question id. */
  answers: Record<string, string>;
  repo_url: string;
  demo_url: string;
  video_url: string;
  disqualified_at?: string | null;
  disqualified_reason?: string;
}

/** An organizer's view of one submitted entry's eligibility. */
export interface EligibilityRow {
  submission_id: number;
  title: string;
  team_name: string;
  disqualified_at: string | null;
  disqualified_reason: string;
  /** Automatic, advisory checks: the organizer still makes every ruling. */
  flags: string[];
}

// --- Phase 2: judging ------------------------------------------------------

export interface Criterion {
  key: string;
  label: string;
  weight: number;
  max_score: number;
  /** What the criterion means - shown to judges and entrants (PLAN.md 10.8). */
  description?: string;
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
  event_id: number;
  event_name: string;
  /** The event's soft judging deadline, if set. */
  due_at?: string | null;
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
}

export interface RubricGroup {
  rubric_id: number;
  rubric_name: string;
  criteria: Criterion[];
}

export interface ScoringSheet {
  assignment_id: number;
  submission_id: number;
  submission_title: string;
  submission_description: string;
  submission_track: string;
  submission_image_url: string | null;
  submission_tagline: string;
  submission_tech_tags: string[];
  submission_images: SubmissionImage[];
  /** Every visible question the team answered, read-only. */
  answers: QuestionAnswer[];
  repo_url: string;
  demo_url: string;
  video_url: string;
  rubrics: RubricGroup[];
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
  tagline: string;
  description: string;
  track: string;
  tech_tags: string[];
  updated_at: string;
  comment_count: number;
  votes: number | null;
  voted_by_me: boolean;
  image_url: string | null;
  /** The whole gallery; filled on the project page only. */
  images: SubmissionImage[];
  /** Answers to questions the organizer made public; project page only. */
  answers: QuestionAnswer[];
  repo_url: string;
  demo_url: string;
  video_url: string;
  /** Prize labels won - empty until results are visible to the viewer (PLAN.md 10.6). */
  awards: string[];
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


// --- Judge invitation (T2 "judge invitation and assignment") ---------------

export type JudgeInviteStatus = 'open' | 'redeemed' | 'expired';

export interface JudgeInvite {
  id: number;
  token: string;
  invited_email: string;
  note: string;
  expires_at: string;
  redeemed_at: string | null;
  redeemed_by_name: string | null;
  status: JudgeInviteStatus;
  event_id: number | null;
  grants_role: 'judge' | 'organizer';
}

/** Deliberately carries no invitee identity — see the backend's InvitePreview. */
export interface JudgeInvitePreview {
  valid: boolean;
  reason: string;
  expires_at: string | null;
  grants_role?: 'judge' | 'organizer';
  event_name?: string | null;
}

export interface JudgeInviteRedeemResult {
  role: Role;
  already_a_judge: boolean;
  event_id: number | null;
  event_name: string | null;
}


/** Mirrors api/app/audit/router.py's AuditEntry (GET /api/audit, organizer+admin). */
export interface AuditEntry {
  id: number;
  actor_id: number | null;
  actor_name: string;
  actor_role: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  detail: Record<string, unknown>;
  created_at: string;
}

/** Shape of GET /api/events/{id}/export.json - the bulk event backup. */
export interface EventBackup {
  event: {
    slug: string;
    name: string;
    description: string;
    start_at: string;
    end_at: string;
    tracks: string[];
    prize_config: Record<string, unknown>;
    voting_enabled: boolean;
    results_hidden_until: string | null;
  };
  rubrics: { name: string; criteria: unknown[] }[];
  /** Members are matched to accounts by email on import (DOGFOOD T4). */
  teams: { name: string; members?: { email: string; name: string }[]; captain_email?: string | null }[];
  submissions: { team_name: string; title: string; description: string; track: string; status: string }[];
  /** The judge panel, assignments and scores: optional, for older backups. */
  judges?: { email: string; name: string; track: string | null }[];
  assignments?: { team_name: string; judge_email: string }[];
  scores?: { team_name: string; judge_email: string; values: Record<string, number>; comment: string }[];
}

/** Password recovery (PLAN.md Phase 9). */
export interface ResetPreview {
  valid: boolean;
  reason: '' | 'unknown' | 'expired' | 'used';
  first_name: string | null;
  email_enabled: boolean;
}

export interface RedeemResult {
  user: User;
  issued_by_name: string | null;
}

export interface IssuedResetLink {
  url: string;
  expires_at: string;
  name: string;
  email: string;
  role: Role;
}

export interface EmailStatus {
  enabled: boolean;
  host: string;
  port: number;
  security: 'starttls' | 'ssl' | 'none';
  sender: string;
  username_set: boolean;
  base_url: string;
}

// --- PLAN.md Phase 10 --------------------------------------------------------

export interface JudgeConflictRecord {
  submission_id: number;
  submission_title: string;
  reason: string;
  created_at: string;
}

export interface EventJudgeRow {
  user_id: number;
  name: string;
  email: string;
  /** One of the event's tracks, or null for a judge who takes any track. */
  track: string | null;
  assigned: number;
  scored: number;
  last_activity: string | null;
  conflicts: JudgeConflictRecord[];
}

export interface EventJudges {
  scored: number;
  assigned: number;
  judges: EventJudgeRow[];
  email_enabled: boolean;
  judging_deadline?: string | null;
}

export interface JudgeEvent {
  event_id: number;
  name: string;
  slug: string;
  end_at: string;
  judging_open: boolean;
  judging_deadline?: string | null;
}

export interface PrizeSlot {
  prize_rank: string;
  reward: string;
  submission_id: number | null;
  note: string;
  suggested_submission_id: number | null;
  track: string | null;
}

export interface AwardCandidate {
  submission_id: number;
  title: string;
  team_name: string;
  track: string;
  rank: number | null;
}

export interface AwardsView {
  prizes: PrizeSlot[];
  results_visible_to_public: boolean;
  candidates: AwardCandidate[];
}

export interface Winner {
  prize_rank: string;
  reward: string;
  submission_id: number;
  title: string;
  team_name: string;
  note: string;
}

export interface WinnersView {
  visible: boolean;
  winners: Winner[];
}

export interface Announcement {
  id: number;
  event_id: number;
  event_name: string;
  event_slug: string;
  title: string;
  body: string;
  author_name: string;
  emailed_count: number;
  created_at: string;
  updated_at: string;
  email_queued: number | null;
}

export interface PublicCriterion {
  rubric: string;
  label: string;
  weight: number;
  max_score: number;
  description: string;
}

export interface AdminUser {
  id: number;
  name: string;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface UserPage {
  users: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface DuplicateMembership {
  event_id: number;
  event_name: string;
  user_id: number;
  user_name: string;
  teams: number;
}
