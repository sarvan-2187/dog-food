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
