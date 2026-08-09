import { redirect } from "next/navigation";

export default function VoiceNotesRedirect() {
  redirect("/dashboard/conversations");
}
