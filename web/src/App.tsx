import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './components/auth/guards';
import { GuidedTour } from './components/GuidedTour';
import { AppFrame } from './components/layout/AppShell';
import { AuthProvider } from './lib/auth-context';
import { DashboardPage } from './pages/DashboardPage';
import { EventCreatePage } from './pages/EventCreatePage';
import { EventDetailPage } from './pages/EventDetailPage';
import { EventResultsPage } from './pages/EventResultsPage';
import { EventSettingsPage } from './pages/EventSettingsPage';
import { EventsPage } from './pages/EventsPage';
import { GalleryPage } from './pages/GalleryPage';
import { JoinTeamPage } from './pages/JoinTeamPage';
import { JudgeDashboardPage } from './pages/JudgeDashboardPage';
import { JudgeInvitePage } from './pages/JudgeInvitePage';
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ProfilePage } from './pages/ProfilePage';
import { RegisterPage } from './pages/RegisterPage';
import { RubricBuilderPage } from './pages/RubricBuilderPage';
import { ScorePage } from './pages/ScorePage';
import { SubmissionDetailPage } from './pages/SubmissionDetailPage';
import { SubmissionPage } from './pages/SubmissionPage';
import { TeamsMinePage } from './pages/TeamsMinePage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { AdminUsersPage } from './pages/AdminUsersPage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppFrame>
          <GuidedTour />
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset/:token" element={<ResetPasswordPage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route
              path="/dashboard"
              element={
                <RequireAuth>
                  <DashboardPage />
                </RequireAuth>
              }
            />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/events/new" element={<EventCreatePage />} />
            <Route path="/events/:slug" element={<EventDetailPage />} />
            <Route path="/events/:slug/rubric" element={<RubricBuilderPage />} />
            <Route path="/events/:slug/settings" element={<EventSettingsPage />} />
            <Route path="/events/:slug/results" element={<EventResultsPage />} />
            <Route path="/events/:slug/gallery" element={<GalleryPage />} />
            <Route path="/judge" element={<JudgeDashboardPage />} />
            <Route path="/judge-invite/:token" element={<JudgeInvitePage />} />
            <Route path="/assignments/:assignmentId/score" element={<ScorePage />} />
            <Route path="/gallery" element={<GalleryPage />} />
            <Route path="/submissions/:submissionId" element={<SubmissionDetailPage />} />
            <Route path="/join/:code" element={<JoinTeamPage />} />
            <Route
              path="/profile"
              element={
                <RequireAuth>
                  <ProfilePage />
                </RequireAuth>
              }
            />
            <Route
              path="/teams/mine"
              element={
                <RequireAuth>
                  <TeamsMinePage />
                </RequireAuth>
              }
            />
            <Route
              path="/teams/:teamId/submission"
              element={
                <RequireAuth>
                  <SubmissionPage />
                </RequireAuth>
              }
            />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </AppFrame>
      </BrowserRouter>
    </AuthProvider>
  );
}

