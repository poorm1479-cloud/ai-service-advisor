import { redirect } from "next/navigation";

/** Memory is now customer History — keep route for old bookmarks. */
export default function MemoryPage() {
  redirect("/dashboard/customers");
}
