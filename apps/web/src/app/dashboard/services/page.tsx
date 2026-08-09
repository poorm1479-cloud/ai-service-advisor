import { redirect } from "next/navigation";

export default function ServicesPageRedirect() {
  redirect("/dashboard/settings?tab=shop");
}
