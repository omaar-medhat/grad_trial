import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  initializeAuth,
  type Auth,
  // @ts-expect-error - getReactNativePersistence is exported at runtime but not
  // surfaced in the Firebase typings.
  getReactNativePersistence,
} from "firebase/auth";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { config } from "@/config";

/**
 * Firebase AUTHENTICATION ONLY for the mobile app.
 *
 * The mobile app uses Firebase Auth purely to sign the user in and learn their
 * uid. It does NOT read the Realtime Database directly (the DB is locked and
 * only the Flask backend, via the Admin SDK, may read it) and it MUST NEVER
 * contain the Firebase Admin SDK or any service-account/private key. All
 * telemetry, alerts, reports, profile and goals come from the backend APIs.
 *
 * The values used here (apiKey/authDomain/projectId/appId) are the PUBLIC
 * Firebase web client config — safe to ship in the bundle.
 */
let _app: FirebaseApp | null = null;
let _auth: Auth | null = null;
let _attempted = false;

function init() {
  if (_attempted) return;
  _attempted = true;
  const c = config.firebase;
  // Auth needs apiKey + authDomain + projectId (+ appId). No databaseURL.
  if (!c.apiKey || !c.authDomain || !c.projectId) {
    console.info("[firebase] auth env missing — demo mode only");
    return;
  }
  try {
    _app = getApps().length ? getApps()[0]! : initializeApp(c);
    try {
      _auth = initializeAuth(_app, {
        persistence: getReactNativePersistence(AsyncStorage),
      });
    } catch {
      // initializeAuth throws if already called (e.g. fast refresh).
      _auth = getAuth(_app);
    }
  } catch (e) {
    console.warn("[firebase] auth init failed", e);
  }
}

export function getFirebaseAuth(): Auth | null {
  init();
  return _auth;
}
