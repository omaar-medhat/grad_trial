import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { getFirebaseDb, fbPath } from "@/integrations/firebase/client";
import { ref, set } from "firebase/database";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Heart } from "lucide-react";

interface OnboardingForm {
  name: string;
  age: string;
  gender: string;
  height_cm: string;
  weight_kg: string;
  activity: string;
}

const EMPTY: OnboardingForm = {
  name: "",
  age: "",
  gender: "",
  height_cm: "",
  weight_kg: "",
  activity: "",
};

const Onboarding = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<OnboardingForm>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!user) return;
    const db = getFirebaseDb();
    if (!db) {
      setError("Firebase is not connected. Please check your configuration.");
      return;
    }

    setSaving(true);
    try {
      const profile = {
        name: form.name.trim(),
        age: parseInt(form.age),
        gender: form.gender,
        height_cm: parseInt(form.height_cm),
        weight_kg: parseInt(form.weight_kg),
        activity: form.activity,
        email: user.email,
        uid: user.id,
        created_at: Date.now(),
        updated_at: Date.now(),
      };

      const goals = { steps: 10000, sleep: 8, calories: 500 };

      await set(ref(db, fbPath.profile(user.id)), profile);
      await set(ref(db, fbPath.goals(user.id)), goals);

      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <Card className="w-full max-w-lg">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Heart className="h-6 w-6 text-primary" />
          </div>
          <CardTitle className="text-2xl">Welcome to PulseGuard AI</CardTitle>
          <p className="text-sm text-muted-foreground">
            Tell us about yourself to personalize your health monitoring experience.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">Full Name</label>
              <Input
                placeholder="Your name"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                required
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium">Age</label>
                <Input
                  type="number"
                  placeholder="Years"
                  min={1}
                  max={120}
                  value={form.age}
                  onChange={e => setForm(f => ({ ...f, age: e.target.value }))}
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Gender</label>
                <Select value={form.gender || undefined} onValueChange={v => setForm(f => ({ ...f, gender: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="male">Male</SelectItem>
                    <SelectItem value="female">Female</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium">Height (cm)</label>
                <Input
                  type="number"
                  placeholder="cm"
                  min={50}
                  max={250}
                  value={form.height_cm}
                  onChange={e => setForm(f => ({ ...f, height_cm: e.target.value }))}
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Weight (kg)</label>
                <Input
                  type="number"
                  placeholder="kg"
                  min={10}
                  max={300}
                  value={form.weight_kg}
                  onChange={e => setForm(f => ({ ...f, weight_kg: e.target.value }))}
                  required
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium">Activity Level</label>
              <Select value={form.activity || undefined} onValueChange={v => setForm(f => ({ ...f, activity: v }))}>
                <SelectTrigger><SelectValue placeholder="Select your activity level" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="sedentary">Sedentary (little/no exercise)</SelectItem>
                  <SelectItem value="light">Light (1-3 days/week)</SelectItem>
                  <SelectItem value="moderate">Moderate (3-5 days/week)</SelectItem>
                  <SelectItem value="active">Active (6-7 days/week)</SelectItem>
                  <SelectItem value="very_active">Very Active (athlete)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}

            <Button
              type="submit"
              className="h-11 w-full text-sm font-semibold"
              disabled={saving || !form.name || !form.age || !form.gender || !form.height_cm || !form.weight_kg || !form.activity}
            >
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Continue
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

export default Onboarding;
