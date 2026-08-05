/**
 * Admin System Health — monitoring layer only.
 * Probes existing public/admin endpoints; does not change backend services.
 */

import { getApiUrl } from "@/lib/api";
import { getAdminSystem, getAdminUsage, type SystemStatus } from "@/lib/admin";

export type HealthLevel = "green" | "yellow" | "red";

export type HealthComponentId =
  | "api"
  | "database"
  | "ai"
  | "sms"
  | "voice"
  | "integrations";

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

async function probeJson(path: string): Promise<{ ok: boolean; status: number; data: unknown }> {
  try {
    const res = await fetch(`${getApiUrl()}${path}`, { cache: "no-store" });
    let data: unknown = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    return { ok: res.ok, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: null };
  }
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

function providerLevel(probe: {
  ok: boolean;
  data: unknown;
  enabledKey: string;
  failureKeys: string[];
}): { level: HealthLevel; detail: string } {
  if (!probe.ok || !probe.data || typeof probe.data !== "object") {
    return { level: "red", detail: "Provider health endpoint unreachable" };
  }
  const body = probe.data as Record<string, unknown>;
  const enabled = body[probe.enabledKey];
  const metrics =
    body.metrics && typeof body.metrics === "object"
      ? (body.metrics as Record<string, unknown>)
      : {};
  const provider = typeof body.provider === "string" ? body.provider : "unknown";
  const failures = probe.failureKeys.reduce((sum, k) => sum + num(metrics[k]), 0);
  const queueDepth = num(body.queue_depth);

  if (enabled === false) {
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
  usageOk: boolean;
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
  if (!args.usageOk) {
    return { level: "yellow", detail: "AI usage monitor unreachable" };
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
  return { level: "green", detail: "API reachable · usage monitor OK" };
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

export async function loadSystemHealth(accessToken: string): Promise<SystemHealthSnapshot> {
  const [apiProbe, readyProbe, smsProbe, voiceProbe, systemResult, usageResult] =
    await Promise.all([
      probeJson("/health"),
      probeJson("/ready"),
      probeJson("/v1/webhooks/twilio/health"),
      probeJson("/v1/webhooks/twilio/voice/health"),
      getAdminSystem(accessToken)
        .then((data) => ({ ok: true as const, data }))
        .catch(() => ({ ok: false as const, data: null })),
      getAdminUsage(accessToken)
        .then(() => true)
        .catch(() => false),
    ]);

  const system = systemResult.ok ? systemResult.data : null;
  const incidents = system?.incidents ?? [];
  const smsMetrics = system?.sms ?? {};
  const voiceMetrics = system?.voice ?? {};

  const apiOk =
    apiProbe.ok &&
    typeof apiProbe.data === "object" &&
    apiProbe.data !== null &&
    (apiProbe.data as { status?: string }).status === "ok";

  const dbCheck =
    system?.readiness?.checks?.database ??
    (readyProbe.data && typeof readyProbe.data === "object"
      ? (readyProbe.data as { checks?: { database?: { status?: string; error?: string } } }).checks
          ?.database
      : undefined);
  const redisCheck =
    system?.readiness?.checks?.redis ??
    (readyProbe.data && typeof readyProbe.data === "object"
      ? (readyProbe.data as { checks?: { redis?: { status?: string; error?: string } } }).checks
          ?.redis
      : undefined);

  const dbUp = dbCheck?.status === "up";
  const redisUp = redisCheck?.status === "up";

  const api: HealthComponent = {
    id: "api",
    label: COMPONENT_LABELS.api,
    level: apiOk ? "green" : "red",
    status: apiOk ? "healthy" : "outage",
    detail: apiOk
      ? `phase ${
          typeof apiProbe.data === "object" && apiProbe.data
            ? String((apiProbe.data as { phase?: string }).phase ?? "—")
            : "—"
        }`
      : "Health probe failed",
  };

  const database: HealthComponent = {
    id: "database",
    label: COMPONENT_LABELS.database,
    level: dbUp ? "green" : "red",
    status: dbUp ? "healthy" : "outage",
    detail: dbUp ? "Connection OK" : dbCheck?.error || "Database check failed",
  };

  const smsProv = providerLevel({
    ok: smsProbe.ok,
    data: smsProbe.data,
    enabledKey: "sms_enabled",
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
    ok: voiceProbe.ok,
    data: voiceProbe.data,
    enabledKey: "voice_enabled",
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
    usageOk: usageResult,
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
    generated_at: system?.generated_at ?? new Date().toISOString(),
    overall,
    components,
    incidents,
    metrics: { sms: smsMetrics, voice: voiceMetrics },
  };
}
