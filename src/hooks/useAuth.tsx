/**
 * Authentication hook — Firebase Email/Password with a one-tap demo fallback.
 *
 * Demo fallback fires automatically when Firebase env vars are missing OR the
 * user clicks "Continue as demo" on the auth screen. Either way, downstream
 * code sees a stable `user.id` it can use as the Realtime DB partition key.
 */

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut as fbSignOut,
  type User as FbUser,
} from "firebase/auth";
import { getFirebaseAuth } from "@/integrations/firebase/client";

export interface AuthUser {
  id: string;
  email: string;
  isDemo: boolean;
}

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  firebaseEnabled: boolean;
  signIn: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  signUp: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  signInDemo: () => void;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<{ ok: boolean; error?: string }>;
}

const DEMO_KEY = "pulseguard:demo-user";
const DEMO_UID = import.meta.env.VITE_DEMO_USER_ID || "demo-user-001";

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  firebaseEnabled: false,
  signIn: async () => ({ ok: false, error: "AuthProvider missing" }),
  signUp: async () => ({ ok: false, error: "AuthProvider missing" }),
  signInDemo: () => {},
  signOut: async () => {},
  resetPassword: async () => ({ ok: false, error: "AuthProvider missing" }),
});

function fromFirebaseUser(u: FbUser): AuthUser {
  return { id: u.uid, email: u.email ?? "", isDemo: false };
}

function readDemoUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(DEMO_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.id ? parsed : null;
  } catch {
    return null;
  }
}

function friendlyError(code: string | undefined, fallback: string): string {
  switch (code) {
    case "auth/invalid-email":         return "That doesn't look like a valid email address.";
    case "auth/user-disabled":         return "This account has been disabled.";
    case "auth/user-not-found":
    case "auth/wrong-password":
    case "auth/invalid-credential":    return "Email or password is incorrect.";
    case "auth/email-already-in-use":  return "An account with this email already exists.";
    case "auth/weak-password":         return "Password should be at least 6 characters.";
    case "auth/network-request-failed":return "Network error — check your connection.";
    case "auth/too-many-requests":     return "Too many attempts. Please wait a minute and try again.";
    default:                           return fallback;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const auth = getFirebaseAuth();
  const firebaseEnabled = auth !== null;

  // Hydrate from Firebase or from cached demo session.
  useEffect(() => {
    if (!auth) {
      const demo = readDemoUser();
      setUser(demo);
      setLoading(false);
      return;
    }
    const unsub = onAuthStateChanged(auth, (fbUser) => {
      if (fbUser) {
        setUser(fromFirebaseUser(fbUser));
      } else {
        // No Firebase user, but maybe the user picked demo earlier.
        setUser(readDemoUser());
      }
      setLoading(false);
    });
    return () => unsub();
  }, [auth]);

  const value: AuthContextType = useMemo(() => ({
    user,
    loading,
    firebaseEnabled,

    signIn: async (email, password) => {
      if (!auth) return { ok: false, error: "Firebase auth is not configured. Tap 'Continue as demo'." };
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
      if (!auth) return { ok: false, error: "Firebase auth is not configured. Tap 'Continue as demo'." };
      try {
        const cred = await createUserWithEmailAndPassword(auth, email.trim(), password);
        setUser(fromFirebaseUser(cred.user));
        return { ok: true };
      } catch (e: unknown) {
        const code = (e as { code?: string }).code;
        return { ok: false, error: friendlyError(code, "Unable to create account.") };
      }
    },

    signInDemo: () => {
      const demo: AuthUser = { id: DEMO_UID, email: "demo@pulseguard.local", isDemo: true };
      localStorage.setItem(DEMO_KEY, JSON.stringify(demo));
      setUser(demo);
    },

    signOut: async () => {
      localStorage.removeItem(DEMO_KEY);
      if (auth && auth.currentUser) {
        try { await fbSignOut(auth); } catch { /* ignore */ }
      }
      setUser(null);
    },

    resetPassword: async (email) => {
      if (!auth) return { ok: false, error: "Firebase auth is not configured." };
      try {
        await sendPasswordResetEmail(auth, email.trim());
        return { ok: true };
      } catch (e: unknown) {
        const code = (e as { code?: string }).code;
        return { ok: false, error: friendlyError(code, "Unable to send reset email.") };
      }
    },
  }), [user, loading, firebaseEnabled, auth]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
