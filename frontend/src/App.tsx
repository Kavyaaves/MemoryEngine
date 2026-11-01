// Routes. Every page except /login sits behind RequireAuth (redirects to /login without a token)
// and inside Layout (sidebar + page area). Pages are lazy-loaded: each one is its own JS file,
// downloaded the first time you open it — so, for example, three.js is only fetched by the Life page.
import { lazy, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { Layout } from "@/components/Layout";
import { RequireAuth } from "@/components/RequireAuth";
import LoginPage from "@/pages/Login/LoginPage";
import { applyTheme, useThemeStore } from "@/stores/themeStore";

const AskPage = lazy(() => import("@/pages/Ask/AskPage"));
const UploadPage = lazy(() => import("@/pages/Upload/UploadPage"));
const LifePage = lazy(() => import("@/pages/Life/LifePage"));
const MemoriesPage = lazy(() => import("@/pages/Memories/MemoriesPage"));
const PeoplePage = lazy(() => import("@/pages/People/PeoplePage"));
const MediaPage = lazy(() => import("@/pages/Media/MediaPage"));
const AILabPage = lazy(() => import("@/pages/AI-Lab/AILabPage"));
const SettingsPage = lazy(() => import("@/pages/Settings/SettingsPage"));

export default function App() {
  const theme = useThemeStore((state) => state.theme);
  useEffect(() => applyTheme(theme), [theme]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/ask" replace />} />
            <Route path="/ask" element={<AskPage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/memories" element={<MemoriesPage />} />
            <Route path="/life" element={<LifePage />} />
            <Route path="/people" element={<PeoplePage />} />
            <Route path="/people/:personId" element={<PeoplePage />} />
            <Route path="/media" element={<MediaPage />} />
            <Route path="/lab" element={<AILabPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/ask" replace />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
