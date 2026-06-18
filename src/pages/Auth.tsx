import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Activity, Heart, ShieldCheck, Mail, Lock, Loader2, PlayCircle, Sparkles,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const Auth = () => {
  const { user, loading, firebaseEnabled, signIn, signUp, signInDemo, resetPassword } = useAuth();
  const { toast } = useToast();
  const [mode, setMode] = useState<"signin" | "signup" | "reset">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (user) return <Navigate to="/" replace />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    if (mode === "reset") {
      const res = await resetPassword(email);
      setSubmitting(false);
      if (res.ok) {
        toast({ title: "Check your email", description: "We've sent a password reset link." });
        setMode("signin");
      } else {
        toast({ title: "Couldn't send the link", description: res.error, variant: "destructive" });
      }
      return;
    }
    const fn = mode === "signin" ? signIn : signUp;
    const res = await fn(email, password);
    setSubmitting(false);
    if (!res.ok) {
      toast({ title: mode === "signin" ? "Sign in failed" : "Sign up failed", description: res.error, variant: "destructive" });
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="grid min-h-screen lg:grid-cols-2">
        {/* ---------------- Left: brand panel (desktop) ---------------- */}
        <aside className="relative hidden overflow-hidden bg-gradient-to-br from-primary/95 via-primary to-accent lg:flex lg:flex-col">
          <div className="absolute inset-0 opacity-20">
            <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-white blur-3xl" />
            <div className="absolute -bottom-40 -right-32 h-96 w-96 rounded-full bg-white blur-3xl" />
          </div>
          <div className="relative flex h-full flex-col p-12 text-primary-foreground">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white shadow-md">
                <img src="/logo.png" alt="" className="h-7 w-7 object-contain" />
              </div>
              <span className="text-lg font-bold tracking-tight">PulseGuard AI</span>
            </div>

            <div className="my-auto max-w-md">
              <h2 className="text-4xl font-bold leading-tight tracking-tight">
                Your health, in clear sight.
              </h2>
              <p className="mt-4 text-base/relaxed text-primary-foreground/85">
                Live readings from your wearable, smart anomaly detection, and a friendly
                AI assistant that explains everything in plain language.
              </p>

              <ul className="mt-8 space-y-3 text-sm">
                {[
                  { icon: Heart, text: "Live heart rate, SpO₂, temperature & sleep" },
                  { icon: ShieldCheck, text: "Instant alerts when something looks off" },
                  { icon: Sparkles, text: "AI health assistant for plain-language insights" },
                  { icon: Activity, text: "Trends and history at a glance" },
                ].map(({ icon: Icon, text }) => (
                  <li key={text} className="flex items-center gap-3 text-primary-foreground/90">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20">
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    {text}
                  </li>
                ))}
              </ul>
            </div>

            <p className="mt-auto text-xs text-primary-foreground/65">
              © {new Date().getFullYear()} PulseGuard AI · Graduation Project
            </p>
          </div>
        </aside>

        {/* ---------------- Right: form ---------------- */}
        <main className="flex items-center justify-center px-6 py-12 sm:px-10">
          <div className="w-full max-w-sm">
            <div className="flex items-center gap-3 lg:hidden">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-card shadow-sm border border-border">
                <img src="/logo.png" alt="" className="h-7 w-7 object-contain" />
              </div>
              <span className="text-base font-bold tracking-tight">PulseGuard AI</span>
            </div>

            <h1 className="mt-8 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              {mode === "reset" ? "Reset your password" : mode === "signin" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {mode === "reset"
                ? "We'll email you a link to set a new password."
                : mode === "signin"
                ? "Sign in to see your live readings and insights."
                : "Join PulseGuard AI to start monitoring your health."}
            </p>

            {!firebaseEnabled && (
              <div className="mt-4 rounded-lg border border-amber-300/50 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                Firebase Authentication isn't configured yet. Use <strong>Continue as guest</strong> below.
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-6 space-y-3">
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-muted-foreground" />
                <Input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="pl-10 h-11"
                  autoComplete="email"
                  required
                />
              </div>
              {mode !== "reset" && (
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    type="password"
                    placeholder="At least 6 characters"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="pl-10 h-11"
                    minLength={6}
                    autoComplete={mode === "signin" ? "current-password" : "new-password"}
                    required
                  />
                </div>
              )}
              <Button
                type="submit"
                className="h-11 w-full text-sm font-semibold shadow-sm"
                disabled={submitting || !firebaseEnabled}
              >
                {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {mode === "reset" ? "Send reset link" : mode === "signin" ? "Sign in" : "Create account"}
              </Button>
            </form>

            <div className="mt-4 flex flex-col items-center gap-2 text-sm">
              {mode === "signin" && (
                <>
                  <button type="button" onClick={() => setMode("signup")} className="font-medium text-primary hover:underline">
                    Don't have an account? Sign up
                  </button>
                  <button type="button" onClick={() => setMode("reset")} className="text-xs text-muted-foreground hover:underline">
                    Forgot password?
                  </button>
                </>
              )}
              {mode === "signup" && (
                <button type="button" onClick={() => setMode("signin")} className="font-medium text-primary hover:underline">
                  Already have an account? Sign in
                </button>
              )}
              {mode === "reset" && (
                <button type="button" onClick={() => setMode("signin")} className="font-medium text-primary hover:underline">
                  Back to sign in
                </button>
              )}
            </div>

            <div className="my-6 flex items-center gap-3 text-[10px] uppercase tracking-wider text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              <span>or</span>
              <span className="h-px flex-1 bg-border" />
            </div>

            <Button
              type="button"
              variant="outline"
              className="h-11 w-full gap-2 border-primary/30 text-primary hover:bg-primary/5"
              onClick={signInDemo}
            >
              <PlayCircle className="h-4 w-4" /> Continue as guest
            </Button>
            <p className="mt-2 text-center text-[11px] leading-relaxed text-muted-foreground">
              Skip the sign-up and explore PulseGuard with simulated readings.
            </p>
          </div>
        </main>
      </div>
    </div>
  );
};

export default Auth;
