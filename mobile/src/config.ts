/**
 * Centralized config + env reading for the mobile app.
 * EXPO_PUBLIC_* env vars are inlined at build time by Expo.
 *
 * This project uses ONLY Firebase Authentication + Firebase Realtime Database.
 * Cloud Firestore and Cloud Storage are NOT used.
 */
const env = (key: string, fallback = ""): string =>
  (process.env[key] as string | undefined) ?? fallback;

export const config = {
  apiBaseUrl: env("EXPO_PUBLIC_API_BASE_URL", "http://10.0.2.2:5000"),
  firebase: {
    apiKey: env("EXPO_PUBLIC_FIREBASE_API_KEY"),
    authDomain: env("EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN"),
    databaseURL: env("EXPO_PUBLIC_FIREBASE_DATABASE_URL"),
    projectId: env("EXPO_PUBLIC_FIREBASE_PROJECT_ID"),
    // storageBucket is part of Firebase web config; Cloud Storage is NOT used.
    storageBucket: env("EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET"),
    messagingSenderId: env("EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID"),
    appId: env("EXPO_PUBLIC_FIREBASE_APP_ID"),
    measurementId: env("EXPO_PUBLIC_FIREBASE_MEASUREMENT_ID"),
  },
  demoMode: env("EXPO_PUBLIC_DEMO_MODE", "false").toLowerCase() === "true",
  demoUid: env("EXPO_PUBLIC_DEMO_USER_ID", "demo-user-001"),
};

export const colors = {
  bg: "#f6f9fb",
  card: "#ffffff",
  text: "#1f2937",
  textMuted: "#6b7280",
  primary: "#198060",
  primarySoft: "#e6f4ee",
  warning: "#f59e0b",
  warningSoft: "#fef3c7",
  danger: "#dc2626",
  dangerSoft: "#fee2e2",
  border: "#e5e7eb",
};
