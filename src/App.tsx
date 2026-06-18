import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, Navigate, useLocation } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { AppLayout } from "@/components/AppLayout";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import Index from "./pages/Index";
import Auth from "./pages/Auth";
import Analytics from "./pages/Analytics";
import Chat from "./pages/Chat";
import Profile from "./pages/Profile";
import Alerts from "./pages/Alerts";
import Onboarding from "./pages/Onboarding";
import NotFound from "./pages/NotFound";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { getFirebaseDb, fbPath } from "@/integrations/firebase/client";
import { ref, get } from "firebase/database";

const queryClient = new QueryClient();

function ProtectedRoute({ children, requireProfile = true }: { children: React.ReactNode; requireProfile?: boolean }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  const [profileStatus, setProfileStatus] = useState<"loading" | "exists" | "missing">("loading");

  useEffect(() => {
    if (loading || !user) return;
    if (!requireProfile || user.isDemo) {
      setProfileStatus("exists");
      return;
    }
    const db = getFirebaseDb();
    if (!db) {
      setProfileStatus("exists");
      return;
    }
    get(ref(db, fbPath.profile(user.id))).then((snap) => {
      const data = snap.val();
      setProfileStatus(data && data.name ? "exists" : "missing");
    }).catch(() => {
      setProfileStatus("exists");
    });
  }, [user, loading, requireProfile]);

  if (loading || (user && requireProfile && profileStatus === "loading")) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!user) return <Navigate to="/auth" replace />;
  if (requireProfile && profileStatus === "missing") {
    return <Navigate to="/onboarding" replace />;
  }
  return (
    <AppLayout>
      <ErrorBoundary key={location.pathname}>{children}</ErrorBoundary>
    </AppLayout>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/auth" element={<Auth />} />
      <Route path="/onboarding" element={<ProtectedRoute requireProfile={false}><Onboarding /></ProtectedRoute>} />
      <Route path="/" element={<ProtectedRoute><Index /></ProtectedRoute>} />
      <Route path="/analytics" element={<ProtectedRoute><Analytics /></ProtectedRoute>} />
      <Route path="/alerts" element={<ProtectedRoute><Alerts /></ProtectedRoute>} />
      <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          {/* Top-level backstop: catches crashes in layout/providers/auth too. */}
          <ErrorBoundary>
            <AppRoutes />
          </ErrorBoundary>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
