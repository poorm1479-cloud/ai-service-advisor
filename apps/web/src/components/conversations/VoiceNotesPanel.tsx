"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { loadSession } from "@/lib/api";
import {
  getAudioUrl,
  listShopVehicles,
  listVoiceNotes,
  uploadVoiceNote,
  VehicleOption,
  VoiceNote,
  VoiceNoteProcessResult,
} from "@/lib/voiceNotes";

export function VoiceNotesPanel() {
  const { session, loading: authLoading } = useAuth();
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  const [vehicles, setVehicles] = useState<VehicleOption[]>([]);
  const [vehicleId, setVehicleId] = useState("");
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VoiceNoteProcessResult | null>(null);
  const [notes, setNotes] = useState<VoiceNote[]>([]);
  const [audioUrls, setAudioUrls] = useState<Record<string, string>>({});
  const [textFallback, setTextFallback] = useState(
    "2019 Honda Accord oil change completed. Brake pads are 30 percent. Recommend replacement next visit. Mileage 82000.",
  );

  useEffect(() => {
    if (authLoading || !session) return;
    void (async () => {
      try {
        setVehicles(await listShopVehicles());
        setNotes(await listVoiceNotes());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      }
    })();
  }, [authLoading, session]);

  async function startRecording() {
    setError(null);
    setResult(null);
    if (!vehicleId) {
      setError("Select a vehicle first");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setError("Microphone permission is required for voice notes");
    }
  }

  async function stopAndUpload() {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;

    setBusy(true);
    setError(null);
    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      recorder.stop();
      setRecording(false);
    });

    try {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      const processed = await uploadVoiceNote(vehicleId, blob, "mechanic-note.webm");
      setResult(processed);
      setNotes(await listVoiceNotes());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function uploadTextAsNote() {
    if (!vehicleId) {
      setError("Select a vehicle first");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const blob = new Blob([textFallback], { type: "text/plain" });
      const processed = await uploadVoiceNote(vehicleId, blob, "mechanic-note.txt");
      setResult(processed);
      setNotes(await listVoiceNotes());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function playAudio(noteId: string) {
    if (audioUrls[noteId]) return;
    const current = loadSession();
    if (!current) {
      setError("Not authenticated");
      return;
    }
    try {
      const res = await fetch(getAudioUrl(noteId), {
        headers: { Authorization: `Bearer ${current.accessToken}` },
      });
      if (!res.ok) throw new Error("Audio fetch failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setAudioUrls((prev) => ({ ...prev, [noteId]: url }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Audio load failed");
    }
  }

  return (
    <div className="min-h-0 flex-1 space-y-8 overflow-y-auto overscroll-contain">
      <p className="text-sm text-[var(--muted)]">
        Speak naturally. The system transcribes, extracts service details, and writes Repair History.
      </p>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <section className="space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Vehicle</span>
          <select
            value={vehicleId}
            onChange={(e) => setVehicleId(e.target.value)}
            className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
          >
            <option value="">Select vehicle…</option>
            {vehicles.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-wrap gap-3">
          {!recording ? (
            <button
              type="button"
              onClick={() => void startRecording()}
              disabled={busy}
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Start speaking
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void stopAndUpload()}
              disabled={busy}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {busy ? "Processing…" : "Stop & process"}
            </button>
          )}
        </div>

        <div className="border-t border-[var(--line)] pt-4">
          <p className="text-sm font-medium">No mic? Paste / edit a spoken note</p>
          <textarea
            value={textFallback}
            onChange={(e) => setTextFallback(e.target.value)}
            rows={4}
            className="mt-2 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
          />
          <button
            type="button"
            onClick={() => void uploadTextAsNote()}
            disabled={busy}
            className="mt-3 rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
          >
            {busy ? "Processing…" : "Process text as voice note"}
          </button>
        </div>
      </section>

      {result && (
        <section className="space-y-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
          <h2 className="text-sm font-semibold">AI result</h2>
          <p className="text-sm">
            <span className="font-medium">Transcript:</span> {result.voice_note.transcript}
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Fact label="Service" value={result.extraction.service} />
            <Fact label="Mileage" value={result.extraction.mileage?.toLocaleString() ?? "—"} />
            <Fact label="Condition" value={result.extraction.condition} />
            <Fact label="Recommendation" value={result.extraction.recommendation ?? "—"} />
          </div>
          <p className="text-sm text-[var(--muted)]">
            Saved repair record{" "}
            <Link
              href={`/dashboard/vehicles/${result.vehicle.id}`}
              className="font-medium text-[var(--accent)]"
            >
              on vehicle page
            </Link>
            .
          </p>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Recent voice notes</h2>
        {notes.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">No voice notes yet</p>
        ) : (
          notes.map((n) => (
            <div key={n.id} className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
              <p className="text-xs text-[var(--muted)]">
                {n.created_at ? new Date(n.created_at).toLocaleString() : "—"}
              </p>
              <p className="mt-2 text-sm">{n.transcript ?? "Processing transcript…"}</p>
              <div className="mt-3">
                {audioUrls[n.id] ? (
                  <audio controls src={audioUrls[n.id]} className="w-full max-w-md" />
                ) : (
                  <button
                    type="button"
                    className="rounded-md border border-[var(--line)] px-3 py-1.5 text-xs"
                    onClick={() => void playAudio(n.id)}
                  >
                    Load audio
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.08em] text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-sm">{value}</p>
    </div>
  );
}
