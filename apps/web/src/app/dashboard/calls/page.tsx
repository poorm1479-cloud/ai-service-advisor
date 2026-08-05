import { redirect } from "next/navigation";

export default function CallsRedirect() {
  redirect("/dashboard/conversations?tab=calls");
}
