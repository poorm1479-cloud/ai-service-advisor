import { clearSession, getApiUrl, loadSession, refresh, saveSession } from "@/lib/api";

async function parseError(res: Response) {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    return JSON.stringify(data.detail ?? data);
  } catch {
    return res.statusText;
  }
}

async function authFetch(path: string, init: RequestInit = {}) {
  let current = loadSession();
  if (!current) throw new Error("Not authenticated");
  const doFetch = (accessToken: string) =>
    fetch(`${getApiUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(init.headers ?? {}),
      },
    });
  let res = await doFetch(current.accessToken);
  if (res.status === 401) {
    try {
      current = await refresh(current.refreshToken);
      saveSession(current);
      res = await doFetch(current.accessToken);
    } catch {
      clearSession();
      throw new Error("Session expired");
    }
  }
  return res;
}

export type CapabilityInfo = {
  capability: string;
  plugin_id?: string;
  plugin_version?: string;
  description?: string;
  [key: string]: unknown;
};

export async function listCapabilities(): Promise<CapabilityInfo[]> {
  const res = await authFetch("/v1/capabilities");
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return (data.capabilities || []) as CapabilityInfo[];
}

export async function invokeCapability(
  capability: string,
  arguments_: Record<string, unknown> = {},
): Promise<{ capability: string; result: unknown; shop_id: string }> {
  const res = await authFetch("/v1/capabilities/invoke", {
    method: "POST",
    body: JSON.stringify({ capability, arguments: arguments_ }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export const LEARNING_CAPS = [
  "CollectDecisionResult",
  "EvaluateDecision",
  "LearnCustomerResponse",
  "AnalyzeSuccessPattern",
  "OptimizeRecommendation",
  "GenerateLearningInsight",
] as const;

export const INSPECTION_CAPS = [
  "AnalyzeInspection",
  "DetectSafetyIssue",
  "GenerateEstimateSuggestion",
  "CreateApprovalRequest",
  "PrioritizeRepair",
  "CreateFollowUp",
  "GenerateInspectionRepairRecommendation",
  "GenerateInspectionCustomerExplanation",
] as const;

export const INVENTORY_CAPS = [
  "FindPart",
  "CheckInventory",
  "PredictRequiredParts",
  "ReservePart",
  "ReleasePart",
  "FindSupplier",
  "CreatePurchaseRecommendation",
  "EstimatePartCost",
  "CheckRepairReadiness",
] as const;

export const ADVISOR_CAPS = [
  "AnalyzeConversation",
  "AnalyzeCustomer",
  "AnalyzeVehicle",
  "GenerateRepairRecommendation",
  "GenerateEstimateSummary",
  "GenerateCustomerExplanation",
  "GenerateApprovalRequest",
  "GenerateRepairUpdate",
  "GenerateFollowUp",
  "GenerateMaintenanceReminder",
  "GenerateReviewRequest",
  "GenerateRetentionPlan",
] as const;
