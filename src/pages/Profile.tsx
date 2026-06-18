import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getFirebaseDb, fbPath } from "@/integrations/firebase/client";
import { onValue, ref, set } from "firebase/database";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Loader2, Save, LogOut, ShieldCheck, User } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface ProfileForm {
  display_name: string;
  date_of_birth: string;
  gender: string;
  blood_type: string;
  emergency_contact: string;
  height_cm: string;
  weight_kg: string;
}

const EMPTY: ProfileForm = {
  display_name: "",
  date_of_birth: "",
  gender: "",
  blood_type: "",
  emergency_contact: "",
  height_cm: "",
  weight_kg: "",
};

const Profile = () => {
  const { user, signOut, firebaseEnabled } = useAuth();
  const { toast } = useToast();
  const [form, setForm] = useState<ProfileForm>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    const db = getFirebaseDb();
    if (!db) { setLoading(false); return; }
    const r = ref(db, fbPath.profile(user.id));
    const unsub = onValue(r, (snap) => {
      const data = snap.val();
      if (data) setForm({ ...EMPTY, ...data });
      setLoading(false);
    }, () => setLoading(false));
    return () => unsub();
  }, [user]);

  const handleSave = async () => {
    if (!user) return;
    const db = getFirebaseDb();
    if (!db) {
      toast({ title: "Demo mode", description: "Sign in with Firebase to save your profile.", variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      await set(ref(db, fbPath.profile(user.id)), {
        ...form,
        updated_at: Date.now(),
      });
      toast({ title: "Profile saved" });
    } catch (e) {
      toast({
        title: "Error",
        description: e instanceof Error ? e.message : "Could not save profile",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
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
        <p className="text-sm text-muted-foreground">
          Personal health info — stored under <code className="text-xs">users/{user?.id}/profile</code> in Realtime DB.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4">
              <Avatar className="h-16 w-16">
                <AvatarFallback className="bg-primary/10 text-primary text-xl">
                  {form.display_name?.charAt(0)?.toUpperCase() || <User className="h-6 w-6" />}
                </AvatarFallback>
              </Avatar>
              <div>
                <CardTitle>{form.display_name || "User"}</CardTitle>
                <p className="text-sm text-muted-foreground">{user?.email}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {user?.isDemo && (
                    <Badge variant="secondary" className="text-[10px]">DEMO MODE</Badge>
                  )}
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
              <label className="mb-1 block text-sm font-medium text-foreground">Display Name</label>
              <Input value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Date of Birth</label>
              <Input type="date" value={form.date_of_birth} onChange={e => setForm(f => ({ ...f, date_of_birth: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Gender</label>
              <Select value={form.gender || undefined} onValueChange={v => setForm(f => ({ ...f, gender: v }))}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="male">Male</SelectItem>
                  <SelectItem value="female">Female</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Blood Type</label>
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
              <label className="mb-1 block text-sm font-medium text-foreground">Height (cm)</label>
              <Input type="number" inputMode="decimal" value={form.height_cm} onChange={e => setForm(f => ({ ...f, height_cm: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Weight (kg)</label>
              <Input type="number" inputMode="decimal" value={form.weight_kg} onChange={e => setForm(f => ({ ...f, weight_kg: e.target.value }))} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Emergency Contact</label>
            <Input placeholder="Name & phone number" value={form.emergency_contact} onChange={e => setForm(f => ({ ...f, emergency_contact: e.target.value }))} />
          </div>
          <Button onClick={handleSave} disabled={saving} className="w-full h-11">
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            Save Profile
          </Button>
          {user?.isDemo && (
            <p className="text-center text-[11px] text-muted-foreground">
              Demo mode: changes are not persisted to a real account.
            </p>
          )}
        </CardContent>
      </Card>

      <p className="text-center text-[11px] text-muted-foreground">
        ⚠️ PulseGuard AI provides health information for educational purposes only and is not a substitute
        for professional medical advice.
      </p>
    </div>
  );
};

export default Profile;
