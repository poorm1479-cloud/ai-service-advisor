/**
 * Admin System Health — derives component levels from /v1/admin/system.
 * One admin endpoint (or its SSE stream) is enough; no multi-endpoint fan-out.
 */

import { getAdminSystem, type SystemStatus } from "@/lib/admin";

export type HealthLevel = "green" | "yellow" | "red";

export type HealthComponentId =
  | "api"
  | "database"
  | "ai"
  | "sms"
  | "voice"
  | "integrations";

/** Feature groups for admin System Health UI */
export type HealthFeatureGroupId =
  | "platform"
  | "ai"
  | "messaging"
  | "voice"
  | "integrations";

export type HealthFeatureGroup = {
  id: HealthFeatureGroupId;
  label: string;
  description: string;
  componentIds: HealthComponentId[];
};

export const HEALTH_FEATURE_GROUPS: HealthFeatureGroup[] = [
  {
    id: "platform",
    label: "Platform",
    description: "Core API and data layer",
    componentIds: ["api", "database"],
  },
  {
    id: "ai",
    label: "AI",
    description: "LLM stack and usage monitor",
    componentIds: ["ai"],
  },
  {
    id: "messaging",
    label: "Messaging",
    description: "SMS provider and runtime",
    componentIds: ["sms"],
  },
  {
    id: "voice",
    label: "Voice",
    description: "Voice provider and runtime",
    componentIds: ["voice"],
  },
  {
    id: "integrations",
    label: "Integrations",
    description: "External shop and billing connectors",
    componentIds: ["integrations"],
  },
];

export type HealthComponent = {
  id: HealthComponentId;
  label: string;
  level: HealthLevel;
  status: string;
  detail: string;
};

export type SystemHealthSnapshot = {
  generated_at: string;
  overall: HealthLevel;
  components: HealthComponent[];
  incidents: SystemStatus["incidents"];
  metrics: {
    sms: Record<string, number | string | null>;
    voice: Record<string, number | string | null>;
  };
};

const COMPONENT_LABELS: Record<HealthComponentId, string> = {
  api: "API",
  database: "Database",
  ai: "AI service",
  sms: "SMS provider",
  voice: "Voice provider",
  integrations: "Integrations",
};

function num(v: unknown): number {
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

function openIncidentsFor(
  incidents: SystemStatus["incidents"],
  keys: string[],
): SystemStatus["incidents"] {
  return incidents.filter(
    (i) =>
      i.status !== "resolved" &&
      i.affected_components.some((c) => keys.some((k) => c.toLowerCase().includes(k))),
  );
}

function worst(...levels: HealthLevel[]): HealthLevel {
  if (levels.includes("red")) return "red";
  if (levels.includes("yellow")) return "yellow";
  return "green";
}

function levelLabel(level: HealthLevel): string {
  if (level === "green") return "healthy";
  if (level === "yellow") return "degraded";
  return "outage";
}

function providerLevel(args: {
  metrics: Record<string, number | string | null>;
  enabled?: boolean;
  provider?: string;
  queueDepth?: number | null;
  failureKeys: string[];
}): { level: HealthLevel; detail: string } {
  const provider = args.provider || "unknown";
  const failures = args.failureKeys.reduce((sum, k) => sum + num(args.metrics[k]), 0);
  const queueDepth = num(args.queueDepth ?? args.metrics.queue_depth);

  if (args.enabled === false) {
    return {
      level: "yellow",
      detail: `Disabled · provider ${provider}`,
    };
  }
  if (failures > 0 || queueDepth > 25) {
    return {
      level: "yellow",
      detail: `Provider ${provider} · ${failures} failures · queue ${queueDepth}`,
    };
  }
  return {
    level: "green",
    detail: `Provider ${provider} · queue ${queueDepth}`,
  };
}

function aiLevel(args: {
  apiOk: boolean;
  incidents: SystemStatus["incidents"];
  sms: Record<string, number | string | null>;
  voice: Record<string, number | string | null>;
}): { level: HealthLevel; detail: string } {
  const aiIncidents = openIncidentsFor(args.incidents, ["ai", "openai", "llm"]);
  const critical = aiIncidents.some((i) => i.severity === "critical" || i.severity === "major");
  if (!args.apiOk) {
    return { level: "red", detail: "API unavailable — AI stack unreachable" };
  }
  if (critical) {
    return {
      level: "red",
      detail: aiIncidents[0]?.title || "Critical AI incident open",
    };
  }
  if (aiIncidents.length > 0) {
    return {
      level: "yellow",
      detail: aiIncidents[0]?.title || "AI incident open",
    };
  }
  const escalations = num(args.sms.escalations) + num(args.voice.escalations);
  if (escalations > 0) {
    return {
      level: "yellow",
      detail: `${escalations} recent AI escalations (SMS/voice)`,
    };
  }
  return { level: "green", detail: "API reachable · no open AI incidents" };
}

function integrationsLevel(args: {
  sms: HealthLevel;
  voice: HealthLevel;
  redis: HealthLevel;
  incidents: SystemStatus["incidents"];
}): { level: HealthLevel; detail: string } {
  const integIncidents = openIncidentsFor(args.incidents, [
    "integration",
    "integrations",
    "stripe",
    "shopmonkey",
    "tekmetric",
    "quickbooks",
  ]);
  const critical = integIncidents.some((i) => i.severity === "critical" || i.severity === "major");
  if (critical) {
    return {
      level: "red",
      detail: integIncidents[0]?.title || "Critical integration incident",
    };
  }
  const providers = worst(args.sms, args.voice);
  const level = worst(providers, args.redis, integIncidents.length > 0 ? "yellow" : "green");
  if (level === "green") {
    return { level, detail: "Communication providers + Redis OK" };
  }
  if (level === "red") {
    return { level, detail: "One or more integration dependencies down" };
  }
  return {
    level,
    detail:
      integIncidents[0]?.title ||
      (args.redis === "yellow" || args.redis === "red"
        ? "Redis degraded — integration queue risk"
        : "Provider or integration warning"),
  };
}

export function healthDotClass(level: HealthLevel): string {
  if (level === "green") return "bg-emerald-500";
  if (level === "yellow") return "bg-amber-400";
  return "bg-red-500";
}

export function healthTextClass(level: HealthLevel): string {
  if (level === "green") return "text-emerald-700";
  if (level === "yellow") return "text-amber-700";
  return "text-red-700";
}

/** Build UI snapshot from a single admin system status payload. */
export function buildSystemHealthFromStatus(system: SystemStatus): SystemHealthSnapshot {
  const incidents = system.incidents ?? [];
  const smsMetrics = system.sms ?? {};
  const voiceMetrics = system.voice ?? {};
  const providers = system.providers ?? {};

  const apiOk = Boolean(system.readiness);
  const env =
    system.readiness && typeof system.readiness === "object"
      ? String((system.readiness as { environment?: string }).environment ?? "—")
      : "—";

  const dbCheck = system.readiness?.checks?.database;
  const redisCheck = system.readiness?.checks?.redis;
  const dbUp = dbCheck?.status === "up";
  const redisUp = redisCheck?.status === "up";

  const api: HealthComponent = {
    id: "api",
    label: COMPONENT_LABELS.api,
    level: apiOk ? "green" : "red",
    status: apiOk ? "healthy" : "outage",
    detail: apiOk ? `env ${env}` : "Admin system endpoint failed",
  };

  const database: HealthComponent = {
    id: "database",
    label: COMPONENT_LABELS.database,
    level: dbUp ? "green" : "red",
    status: dbUp ? "healthy" : "outage",
    detail: dbUp ? "Connection OK" : dbCheck?.error || "Database check failed",
  };

  const smsProv = providerLevel({
    metrics: smsMetrics,
    enabled: providers.sms?.enabled,
    provider: providers.sms?.provider,
    queueDepth: providers.sms?.queue_depth,
    failureKeys: ["queue_failures", "webhook_rejected"],
  });
  const sms: HealthComponent = {
    id: "sms",
    label: COMPONENT_LABELS.sms,
    level: smsProv.level,
    status: levelLabel(smsProv.level),
    detail: smsProv.detail,
  };

  const voiceProv = providerLevel({
    metrics: voiceMetrics,
    enabled: providers.voice?.enabled,
    provider: providers.voice?.provider,
    queueDepth: providers.voice?.queue_depth,
    failureKeys: ["webhook_rejected"],
  });
  const voice: HealthComponent = {
    id: "voice",
    label: COMPONENT_LABELS.voice,
    level: voiceProv.level,
    status: levelLabel(voiceProv.level),
    detail: voiceProv.detail,
  };

  const aiProv = aiLevel({
    apiOk,
    incidents,
    sms: smsMetrics,
    voice: voiceMetrics,
  });
  const ai: HealthComponent = {
    id: "ai",
    label: COMPONENT_LABELS.ai,
    level: aiProv.level,
    status: levelLabel(aiProv.level),
    detail: aiProv.detail,
  };

  const redisLevel: HealthLevel = redisCheck
    ? redisUp
      ? "green"
      : "yellow"
    : apiOk
      ? "yellow"
      : "red";

  const integProv = integrationsLevel({
    sms: sms.level,
    voice: voice.level,
    redis: redisLevel,
    incidents,
  });
  const integrations: HealthComponent = {
    id: "integrations",
    label: COMPONENT_LABELS.integrations,
    level: integProv.level,
    status: levelLabel(integProv.level),
    detail: integProv.detail,
  };

  const components = [api, database, ai, sms, voice, integrations];
  const overall = worst(...components.map((c) => c.level));

  return {
    generated_at: system.generated_at ?? new Date().toISOString(),
    overall,
    components,
    incidents,
    metrics: { sms: smsMetrics, voice: voiceMetrics },
  };
}

export async function loadSystemHealth(accessToken: string): Promise<SystemHealthSnapshot> {
  const system = await getAdminSystem(accessToken);
  return buildSystemHealthFromStatus(system);
}
