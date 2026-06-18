import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

let mockUser: unknown = { id: "u1", email: "a@b.com", isDemo: true };

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: mockUser, signOut: vi.fn(), firebaseEnabled: false,
  }),
}));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));
// No live Firebase in tests → the page must still render (not hang/crash).
vi.mock("@/integrations/firebase/client", () => ({
  getFirebaseDb: () => null,
  fbPath: { profile: (u: string) => `users/${u}/profile` },
}));

import Profile from "./Profile";

describe("Profile page — never crashes", () => {
  beforeEach(() => { mockUser = { id: "u1", email: "a@b.com", isDemo: true }; });

  it("renders without crashing when no Firebase profile/goals exist", () => {
    render(<Profile />);
    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    // Safe defaults: empty form, no thrown error.
    expect(screen.getByText(/save profile/i)).toBeInTheDocument();
  });

  it("renders without crashing when the user is null", () => {
    mockUser = null;
    // Should not throw (shows a loading state rather than blanking).
    expect(() => render(<Profile />)).not.toThrow();
  });
});
