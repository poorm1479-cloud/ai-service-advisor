import { redirect } from "next/navigation";

export default function TeamPageRedirect() {
  redirect("/dashboard/settings?tab=team");
}
