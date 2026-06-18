import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getFirebaseDb, fbPath } from "@/integrations/firebase/client";
import { onValue, ref, set } from "firebase/database";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Loader2, Save, LogOut, ShieldCheck, User, Camera, Target } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface ProfileForm {
  name: string;
  age: string;
  gender: string;
  height_cm: string;
  weight_kg: string;
  activity: string;
  blood_type: string;
  emergency_contact: string;
  photo: string;
}

interface GoalsForm {
  steps: string;
  sleep: string;
  calories: string;
}

const EMPTY_PROFILE: ProfileForm = {
  name: "",
  age: "",
  gender: "",
  height_cm: "",
  weight_kg: "",
  activity: "",
  blood_type: "",
  emergency_contact: "",
  photo: "",
};

const DEFAULT_GOALS: GoalsForm = {
  steps: "10000",
  sleep: "8",
  calories: "500",
};

const Profile = () => {
  const { user, signOut, firebaseEnabled } = useAuth();
  const { toast } = useToast();
  const [form, setForm] = useState<ProfileForm>(EMPTY_PROFILE);
  const [goals, setGoals] = useState<GoalsForm>(DEFAULT_GOALS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingGoals, setSavingGoals] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!user) return;
    const db = getFirebaseDb();
    if (!db) { setLoading(false); return; }

    let loaded = 0;
    const done = () => { loaded++; if (loaded >= 2) setLoading(false); };

    const profileRef = ref(db, fbPath.profile(user.id));
    const unsubProfile = onValue(profileRef, (snap) => {
      const data = snap.val();
      if (data) {
        setForm({
          name: data.name || data.display_name || "",
          age: data.age?.toString() || "",
          gender: data.gender || "",
          height_cm: data.height_cm?.toString() || "",
          weight_kg: data.weight_kg?.toString() || "",
          activity: data.activity || "",
          blood_type: data.blood_type || "",
          emergency_contact: data.emergency_contact || "",
          photo: data.photo || "",
        });
      }
      done();
    }, () => done());

    const goalsRef = ref(db, fbPath.goals(user.id));
    const unsubGoals = onValue(goalsRef, (snap) => {
      const data = snap.val();
      if (data) {
        setGoals({
          steps: data.steps?.toString() || "10000",
          sleep: data.sleep?.toString() || "8",
          calories: data.calories?.toString() || "500",
        });
      }
      done();
    }, () => done());

    return () => { unsubProfile(); unsubGoals(); };
  }, [user]);

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 200 * 1024) {
      toast({ title: "Image too large", description: "Please choose an image under 200KB.", variant: "destructive" });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setForm(f => ({ ...f, photo: reader.result as string }));
    };
    reader.readAsDataURL(file);
  };

  const handleSaveProfile = async () => {
    if (!user) return;
    const db = getFirebaseDb();
    if (!db) {
      toast({ title: "Demo mode", description: "Sign in with Firebase to save your profile.", variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      await set(ref(db, fbPath.profile(user.id)), {
        name: form.name.trim(),
        age: parseInt(form.age) || null,
        gender: form.gender,
        height_cm: parseInt(form.height_cm) || null,
        weight_kg: parseInt(form.weight_kg) || null,
        activity: form.activity,
        blood_type: form.blood_type,
        emergency_contact: form.emergency_contact,
        photo: form.photo,
        email: user.email,
        uid: user.id,
        updated_at: Date.now(),
      });
      toast({ title: "Profile saved" });
    } catch (e) {
      toast({ title: "Error", description: e instanceof Error ? e.message : "Could not save profile", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveGoals = async () => {
    if (!user) return;
    const db = getFirebaseDb();
    if (!db) return;
    setSavingGoals(true);
    try {
      await set(ref(db, fbPath.goals(user.id)), {
        steps: parseInt(goals.steps) || 10000,
        sleep: parseInt(goals.sleep) || 8,
        calories: parseInt(goals.calories) || 500,
      });
      toast({ title: "Goals saved" });
    } catch (e) {
      toast({ title: "Error", description: e instanceof Error ? e.message : "Could not save goals", variant: "destructive" });
    } finally {
      setSavingGoals(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Profile</h2>
        <p className="text-sm text-muted-foreground">Manage your personal info and health goals.</p>
      </div>

      {/* Profile Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4">
              <div className="relative group">
                <Avatar className="h-16 w-16 cursor-pointer" onClick={() => fileRef.current?.click()}>
                  {form.photo ? (
                    <AvatarImage src={form.photo} alt="Profile" />
                  ) : (
                    <AvatarFallback className="bg-primary/10 text-primary text-xl">
                      {form.name?.charAt(0)?.toUpperCase() || <User className="h-6 w-6" />}
                    </AvatarFallback>
                  )}
                </Avatar>
                <div
                  className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                  onClick={() => fileRef.current?.click()}
                >
                  <Camera className="h-5 w-5 text-white" />
                </div>
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handlePhotoUpload} />
              </div>
              <div>
                <CardTitle>{form.name || "User"}</CardTitle>
                <p className="text-sm text-muted-foreground">{user?.email}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {user?.isDemo && <Badge variant="secondary" className="text-[10px]">DEMO MODE</Badge>}
                  {firebaseEnabled && !user?.isDemo && (
                    <Badge variant="outline" className="text-[10px] border-primary/40 text-primary">
                      <ShieldCheck className="mr-1 h-3 w-3" /> Firebase Auth
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <Button variant="ghost" size="sm" className="text-destructive" onClick={signOut}>
              <LogOut className="mr-2 h-4 w-4" /> Sign out
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium">Full Name</label>
              <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Age</label>
              <Input type="number" min={1} max={120} value={form.age} onChange={e => setForm(f => ({ ...f, age: e.target.value }))} />
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
            <div>
              <label className="mb-1 block text-sm font-medium">Activity Level</label>
              <Select value={form.activity || undefined} onValueChange={v => setForm(f => ({ ...f, activity: v }))}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="sedentary">Sedentary</SelectItem>
                  <SelectItem value="light">Light</SelectItem>
                  <SelectItem value="moderate">Moderate</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="very_active">Very Active</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Height (cm)</label>
              <Input type="number" min={50} max={250} value={form.height_cm} onChange={e => setForm(f => ({ ...f, height_cm: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Weight (kg)</label>
              <Input type="number" min={10} max={300} value={form.weight_kg} onChange={e => setForm(f => ({ ...f, weight_kg: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Blood Type</label>
              <Select value={form.blood_type || undefined} onValueChange={v => setForm(f => ({ ...f, blood_type: v }))}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"].map(t => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Emergency Contact</label>
              <Input placeholder="Name & phone" value={form.emergency_contact} onChange={e => setForm(f => ({ ...f, emergency_contact: e.target.value }))} />
            </div>
          </div>
          <Button onClick={handleSaveProfile} disabled={saving} className="w-full h-11">
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            Save Profile
          </Button>
        </CardContent>
      </Card>

      {/* Goals Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            <CardTitle>Daily Goals</CardTitle>
          </div>
          <p className="text-sm text-muted-foreground">Set your personal targets for steps, sleep, and calories.</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Steps / day</label>
              <Input type="number" min={0} value={goals.steps} onChange={e => setGoals(g => ({ ...g, steps: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Sleep (hours)</label>
              <Input type="number" min={0} max={24} value={goals.sleep} onChange={e => setGoals(g => ({ ...g, sleep: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Calories (kcal)</label>
              <Input type="number" min={0} value={goals.calories} onChange={e => setGoals(g => ({ ...g, calories: e.target.value }))} />
            </div>
          </div>
          <Button onClick={handleSaveGoals} disabled={savingGoals} className="w-full h-11" variant="outline">
            {savingGoals ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Target className="mr-2 h-4 w-4" />}
            Save Goals
          </Button>
        </CardContent>
      </Card>

      <p className="text-center text-[11px] text-muted-foreground">
        PulseGuard AI provides health information for educational purposes only and is not a substitute
        for professional medical advice.
      </p>
    </div>
  );
};

export default Profile;
