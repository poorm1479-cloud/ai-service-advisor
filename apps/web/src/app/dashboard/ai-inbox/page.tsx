import { redirect } from "next/navigation";

export default function AiInboxRedirect() {
  redirect("/dashboard/conversations?tab=calls");
}
