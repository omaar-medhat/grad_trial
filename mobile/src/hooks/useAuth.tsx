import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut as fbSignOut,
  type User as FbUser,
} from "firebase/auth";
import { config } from "@/config";
import { getFirebaseAuth } from "@/lib/firebase";
import { setAuthTokenGetter } from "@/lib/api";

export interface AuthUser { id: string; email: string; isDemo: boolean }

interface Ctx {
  user: AuthUser | null;
  loading: boolean;
  firebaseEnabled: boolean;
  signIn: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  signUp: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  resetPassword: (email: string) => Promise<{ ok: boolean; error?: string }>;
  signInDemo: () => void;
  signOut: () => Promise<void>;
}

const DEMO_KEY = "pulseguard:demo-user";

const AuthCtx = createContext<Ctx>({} as Ctx);

function fromFirebaseUser(u: FbUser): AuthUser {
  return { id: u.uid, email: u.email ?? "", isDemo: false };
}

function friendlyError(code: string | undefined, fallback: string): string {
  switch (code) {
    case "auth/invalid-email":         return "Invalid email address.";
    case "auth/user-not-found":
    case "auth/wrong-password":
    case "auth/invalid-credential":    return "Email or password is incorrect.";
    case "auth/email-already-in-use":  return "Account already exists.";
    case "auth/weak-password":         return "Password should be at least 6 characters.";
    case "auth/network-request-failed":return "Network error — check your connection.";
    case "auth/too-many-requests":     return "Too many attempts. Wait a minute and try again.";
    default:                           return fallback;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const auth = getFirebaseAuth();
  const firebaseEnabled = auth !== null;

  // Give the API client a way to fetch a fresh Firebase ID token. Real
  // (non-demo) signed-in users get a token; demo users get null (the backend
  // then uses its demo fallback). getIdToken() auto-refreshes/caches.
  useEffect(() => {
    setAuthTokenGetter(async () => {
      try {
        const u = auth?.currentUser;
        return u ? await u.getIdToken() : null;
      } catch {
        return null;
      }
    });
    return () => setAuthTokenGetter(null);
  }, [auth]);

  useEffect(() => {
    let cancelled = false;

    // Hydrate possible demo session even if Firebase is configured (user picked demo).
    AsyncStorage.getItem(DEMO_KEY).then(raw => {
      if (cancelled) return;
      if (raw) {
        try {
          const parsed = JSON.parse(raw);
          if (parsed?.id) setUser(parsed);
        } catch { /* ignore */ }
      }
      if (!auth) {
        setLoading(false);
      }
    });

    if (!auth) return;

    const unsub = onAuthStateChanged(auth, (fbUser) => {
      if (cancelled) return;
      if (fbUser) {
        setUser(fromFirebaseUser(fbUser));
        // Real auth wins — drop any stale demo cache.
        AsyncStorage.removeItem(DEMO_KEY).catch(() => {});
      }
      setLoading(false);
    });

    return () => { cancelled = true; unsub(); };
  }, [auth]);

  const value: Ctx = useMemo(() => ({
    user,
    loading,
    firebaseEnabled,
    signIn: async (email, password) => {
      if (!auth) return { ok: false, error: "Firebase auth not configured. Tap 'Continue as demo'." };
      try {
        const cred = await signInWithEmailAndPassword(auth, email.trim(), password);
        setUser(fromFirebaseUser(cred.user));
        return { ok: true };
      } catch (e: unknown) {
        const code = (e as { code?: string }).code;
        return { ok: false, error: friendlyError(code, "Unable to sign in.") };
      }
    },
    signUp: async (email, password) => {
      if (!auth) return { ok: false, error: "Firebase auth not configured. Tap 'Continue as demo'." };
      try {
        const cred = await createUserWithEmailAndPassword(auth, email.trim(), password);
        setUser(fromFirebaseUser(cred.user));
        return { ok: true };
      } catch (e: unknown) {
        const code = (e as { code?: string }).code;
        return { ok: false, error: friendlyError(code, "Unable to create account.") };
      }
    },
    resetPassword: async (email) => {
      if (!auth) return { ok: false, error: "Firebase auth not configured." };
      try {
        await sendPasswordResetEmail(auth, email.trim());
        return { ok: true };
      } catch (e: unknown) {
        const code = (e as { code?: string }).code;
        return { ok: false, error: friendlyError(code, "Unable to send reset email.") };
      }
    },
    signInDemo: () => {
      const demo: AuthUser = { id: config.demoUid, email: "demo@pulseguard.local", isDemo: true };
      AsyncStorage.setItem(DEMO_KEY, JSON.stringify(demo)).catch(() => {});
      setUser(demo);
    },
    signOut: async () => {
      await AsyncStorage.removeItem(DEMO_KEY).catch(() => {});
      if (auth?.currentUser) {
        try { await fbSignOut(auth); } catch { /* ignore */ }
      }
      setUser(null);
    },
  }), [user, loading, firebaseEnabled, auth]);

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
