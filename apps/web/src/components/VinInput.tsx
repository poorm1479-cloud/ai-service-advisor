"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const VIN_EXACT_RE = /^[A-HJ-NPR-Z0-9]{17}$/;
/** VIN label with common OCR noise (V1N / VlN / V I N). */
const VIN_LABELED_RE = /V[\s]*[I1L|][\s]*N[\s\-:_=]*([A-HJ-NPR-Z0-9]{17})/i;
const VIN_CHAR_WHITELIST = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789";

/** DecodeHintType numeric values from @zxing/library (peer of @zxing/browser). */
const HINT_POSSIBLE_FORMATS = 2;
const HINT_TRY_HARDER = 3;
const HINT_PURE_BARCODE = 1;

type ZxingBrowser = typeof import("@zxing/browser");
type ZxingReader = InstanceType<ZxingBrowser["BrowserMultiFormatReader"]>;

/** Lazy-load zxing only when the camera scanner starts (keeps customer nav light). */
let zxingModulePromise: Promise<ZxingBrowser> | null = null;
function loadZxing(): Promise<ZxingBrowser> {
  if (!zxingModulePromise) {
    zxingModulePromise = import("@zxing/browser");
  }
  return zxingModulePromise;
}

function releaseZxingStreams(): void {
  void loadZxing()
    .then(({ BrowserCodeReader }) => {
      BrowserCodeReader.releaseAllStreams();
    })
    .catch(() => undefined);
}

const NATIVE_BARCODE_FORMATS = [
  "code_39",
  "code_128",
  "pdf417",
  "qr_code",
  "data_matrix",
  "codabar",
  "itf",
] as const;

const VIN_TRANSLITERATION: Record<string, number> = {
  "0": 0,
  "1": 1,
  "2": 2,
  "3": 3,
  "4": 4,
  "5": 5,
  "6": 6,
  "7": 7,
  "8": 8,
  "9": 9,
  A: 1,
  B: 2,
  C: 3,
  D: 4,
  E: 5,
  F: 6,
  G: 7,
  H: 8,
  J: 1,
  K: 2,
  L: 3,
  M: 4,
  N: 5,
  P: 7,
  R: 9,
  S: 2,
  T: 3,
  U: 4,
  V: 5,
  W: 6,
  X: 7,
  Y: 8,
  Z: 9,
};
const VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2];

function hasValidVinCheckDigit(vin: string): boolean {
  let total = 0;
  for (let i = 0; i < 17; i++) {
    const value = VIN_TRANSLITERATION[vin[i]];
    if (value === undefined) return false;
    total += value * VIN_WEIGHTS[i];
  }
  const remainder = total % 11;
  const expected = remainder === 10 ? "X" : String(remainder);
  return vin[8] === expected;
}

function collectVinCandidates(cleaned: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (let i = 0; i <= cleaned.length - 17; i++) {
    const slice = cleaned.slice(i, i + 17);
    if (!VIN_EXACT_RE.test(slice) || seen.has(slice)) continue;
    seen.add(slice);
    out.push(slice);
  }
  return out;
}

function pickVin(
  candidates: string[],
  labeled: string | null,
  requireCheckDigit: boolean,
): string | null {
  const valid = candidates.find(hasValidVinCheckDigit);
  if (valid) return valid;
  if (requireCheckDigit) return null;
  if (labeled) return labeled;
  return candidates[0] ?? null;
}

/** Normalize OCR confusions: O/Q→0, I/|→1 (invalid VIN letters). */
export function normalizeOcrVinText(raw: string): string {
  return raw
    .toUpperCase()
    .replace(/[OQ]/g, "0")
    .replace(/[I|]/g, "1")
    // Common OCR noise that is never a VIN character.
    .replace(/[^A-HJ-NPR-Z0-9\s\-_:]/g, "");
}

/** Strip barcode wrappers / GS1 noise before VIN extraction. */
function normalizeBarcodePayload(raw: string): string {
  return raw
    .toUpperCase()
    .replace(/[\u0000-\u001F]/g, " ")
    .replace(/[OQ]/g, "0")
    .replace(/\bVIN\b[\s\-:_=]*/g, "VIN ")
    .trim();
}

function gatherVinCandidates(upper: string): { candidates: string[]; labeled: string | null } {
  const labeled = upper.match(VIN_LABELED_RE)?.[1] ?? null;
  const tokenCandidates: string[] = [];
  for (const token of upper.split(/[^A-HJ-NPR-Z0-9]+/)) {
    if (token.length === 17 && VIN_EXACT_RE.test(token)) {
      tokenCandidates.push(token);
    } else if (token.length > 17 && token.length <= 40) {
      // Door-jamb barcodes often prefix/suffix a few chars around the VIN.
      tokenCandidates.push(...collectVinCandidates(token));
    }
  }
  const cleaned = upper.replace(/[\s\-:_]/g, "");
  const looseCandidates = VIN_EXACT_RE.test(cleaned)
    ? [cleaned]
    : cleaned.length >= 17 && cleaned.length <= 40
      ? collectVinCandidates(cleaned)
      : [];
  // Prefer exact tokens, then labeled, then sliding windows.
  const ordered = [...tokenCandidates, ...looseCandidates];
  const seen = new Set<string>();
  const candidates = ordered.filter((c) => {
    if (seen.has(c)) return false;
    seen.add(c);
    return true;
  });
  return { candidates, labeled };
}

/**
 * Barcode/QR payloads — prefer ISO check digit.
 * Format-only fallback only for an exact 17-char token (not a sliding window).
 */
export function extractVin(raw: string): string | null {
  const upper = normalizeBarcodePayload(raw);
  const { candidates, labeled } = gatherVinCandidates(upper);
  if (labeled && hasValidVinCheckDigit(labeled)) return labeled;

  const withCheck = pickVin(candidates, labeled, true);
  if (withCheck) return withCheck;

  if (labeled && VIN_EXACT_RE.test(labeled)) return labeled;

  // Exact token only — avoids grabbing 17 chars out of a longer noisy string.
  for (const token of upper.split(/[^A-HJ-NPR-Z0-9]+/)) {
    if (token.length === 17 && VIN_EXACT_RE.test(token)) return token;
  }
  return null;
}

/** Common OCR lookalikes — only accept when the repair is unique. */
const OCR_CHAR_ALTS: Record<string, string[]> = {
  B: ["8"],
  "8": ["B"],
  S: ["5"],
  "5": ["S"],
  Z: ["2"],
  "2": ["Z"],
  G: ["6"],
  "6": ["G"],
  D: ["0"],
  "0": ["D"],
  T: ["7"],
  "7": ["T"],
  Y: ["4"],
  "4": ["Y"],
};

function repairVinByCheckDigit(vin: string): string | null {
  if (!VIN_EXACT_RE.test(vin)) return null;
  if (hasValidVinCheckDigit(vin)) return vin;

  const singles = new Set<string>();
  for (let i = 0; i < 17; i++) {
    const alts = OCR_CHAR_ALTS[vin[i]];
    if (!alts) continue;
    for (const alt of alts) {
      const next = `${vin.slice(0, i)}${alt}${vin.slice(i + 1)}`;
      if (VIN_EXACT_RE.test(next) && hasValidVinCheckDigit(next)) singles.add(next);
    }
  }
  if (singles.size === 1) return singles.values().next().value ?? null;

  // Blurry OCR often flips 2 lookalike chars — accept only if unique.
  const doubles = new Set<string>();
  for (let i = 0; i < 17; i++) {
    const altsI = OCR_CHAR_ALTS[vin[i]];
    if (!altsI) continue;
    for (const altI of altsI) {
      const once = `${vin.slice(0, i)}${altI}${vin.slice(i + 1)}`;
      for (let j = i + 1; j < 17; j++) {
        const altsJ = OCR_CHAR_ALTS[once[j]];
        if (!altsJ) continue;
        for (const altJ of altsJ) {
          const twice = `${once.slice(0, j)}${altJ}${once.slice(j + 1)}`;
          if (VIN_EXACT_RE.test(twice) && hasValidVinCheckDigit(twice)) doubles.add(twice);
        }
      }
    }
  }
  if (doubles.size === 1) return doubles.values().next().value ?? null;
  return null;
}

/**
 * Printed VIN OCR — only accept ISO 3779 check-digit matches.
 * Rejects nearby labels/part numbers that merely look VIN-shaped.
 */
function extractVinFromOcr(raw: string): string | null {
  const upper = normalizeOcrVinText(raw);
  const { candidates, labeled } = gatherVinCandidates(upper);
  if (labeled && hasValidVinCheckDigit(labeled)) return labeled;
  if (labeled) {
    const repairedLabeled = repairVinByCheckDigit(labeled);
    if (repairedLabeled) return repairedLabeled;
  }
  const exact = pickVin(candidates, labeled, true);
  if (exact) return exact;
  for (const candidate of candidates) {
    const repaired = repairVinByCheckDigit(candidate);
    if (repaired) return repaired;
  }
  return null;
}

type VinInputProps = {
  value: string;
  onChange: (vin: string) => void;
  status?: string | null;
  looking?: boolean;
  required?: boolean;
};

type ScannerControls = { stop: () => void };

type OcrWorker = {
  recognize: (image: HTMLCanvasElement) => Promise<{ data: { text: string } }>;
  setParameters: (params: Record<string, string>) => Promise<unknown>;
  terminate: () => Promise<unknown>;
};

async function createVinReader(pureBarcode = false): Promise<ZxingReader> {
  const { BarcodeFormat, BrowserMultiFormatReader } = await loadZxing();
  const formats = [
    BarcodeFormat.CODE_39,
    BarcodeFormat.CODE_128,
    BarcodeFormat.PDF_417,
    BarcodeFormat.QR_CODE,
    BarcodeFormat.DATA_MATRIX,
    BarcodeFormat.CODABAR,
    BarcodeFormat.ITF,
  ];
  const hints = new Map<number, unknown>();
  hints.set(HINT_TRY_HARDER, true);
  hints.set(HINT_POSSIBLE_FORMATS, formats);
  if (pureBarcode) hints.set(HINT_PURE_BARCODE, true);
  return new BrowserMultiFormatReader(
    hints as ConstructorParameters<typeof BrowserMultiFormatReader>[0],
  );
}

async function waitForVideoReady(
  video: HTMLVideoElement,
  cancelled: () => boolean,
): Promise<boolean> {
  // Mobile cameras often report <640px briefly (or stay at 480p). Accept any frames.
  for (let i = 0; i < 100; i++) {
    if (cancelled()) return false;
    if (
      video.videoWidth > 0 &&
      video.videoHeight > 0 &&
      video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
    ) {
      return true;
    }
    await new Promise((r) => window.setTimeout(r, 50));
  }
  return video.videoWidth > 0 && video.videoHeight > 0;
}

/** iOS Safari needs playsinline + muted before play(), or the preview stays black. */
async function attachStreamToVideo(
  video: HTMLVideoElement,
  stream: MediaStream,
): Promise<void> {
  video.setAttribute("playsinline", "true");
  video.setAttribute("webkit-playsinline", "true");
  video.playsInline = true;
  video.muted = true;
  video.defaultMuted = true;
  video.srcObject = stream;
  try {
    await video.play();
  } catch {
    await new Promise((r) => window.setTimeout(r, 120));
    await video.play().catch(() => undefined);
  }
}

function waitForVideoElement(
  getVideo: () => HTMLVideoElement | null,
  cancelled: () => boolean,
): Promise<HTMLVideoElement | null> {
  return new Promise((resolve) => {
    const existing = getVideo();
    if (existing) {
      resolve(existing);
      return;
    }
    let frames = 0;
    const tick = () => {
      if (cancelled()) {
        resolve(null);
        return;
      }
      const el = getVideo();
      if (el) {
        resolve(el);
        return;
      }
      frames += 1;
      if (frames > 30) {
        resolve(null);
        return;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function cameraErrorMessage(err: unknown): string {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return "Camera needs HTTPS (or localhost). Open this page over a secure connection, or type the VIN.";
  }
  const name = err instanceof DOMException || err instanceof Error ? err.name : "";
  const message = err instanceof Error ? err.message : "Camera access failed";
  if (name === "NotAllowedError" || /NotAllowedError|Permission/i.test(message)) {
    return "Camera permission denied. Allow camera access or type the VIN.";
  }
  if (name === "NotFoundError" || /NotFoundError|no.*camera|Requested device not found/i.test(message)) {
    return "No camera found. Type the VIN manually instead.";
  }
  if (
    name === "OverconstrainedError" ||
    name === "ConstraintNotSatisfiedError" ||
    /Overconstrained|Could not start video source/i.test(message)
  ) {
    return "Could not open the rear camera. Close other apps using the camera, or type the VIN.";
  }
  if (name === "NotReadableError" || /NotReadableError|in use/i.test(message)) {
    return "Camera is in use by another app. Close it and try again, or type the VIN.";
  }
  return message;
}

type PreprocessMode = "raw" | "contrast" | "binary" | "invert" | "reflect" | "sharpen";

type ScanPreset = {
  /** Smaller widthFrac = more digital zoom (better at distance). */
  widthFrac: number;
  heightFrac: number;
  targetWidth: number;
  mode: PreprocessMode;
};

type FrameQuality = {
  sharpness: number;
  motion: number;
  glareRatio: number;
  stable: boolean;
  sharpEnough: boolean;
  glareHeavy: boolean;
};

/** Close-up: wide/tall band so large VIN letters are not clipped. */
const NEAR_OCR_PRESETS: ScanPreset[] = [
  { widthFrac: 0.92, heightFrac: 0.22, targetWidth: 1400, mode: "sharpen" },
  { widthFrac: 0.92, heightFrac: 0.22, targetWidth: 1400, mode: "reflect" },
  { widthFrac: 0.92, heightFrac: 0.22, targetWidth: 1400, mode: "contrast" },
  { widthFrac: 0.92, heightFrac: 0.22, targetWidth: 1400, mode: "binary" },
  { widthFrac: 0.92, heightFrac: 0.22, targetWidth: 1400, mode: "invert" },
];

/** Mid / far: tighter crops with heavy upscale. */
const FAR_OCR_PRESETS: ScanPreset[] = [
  { widthFrac: 0.32, heightFrac: 0.06, targetWidth: 1800, mode: "sharpen" },
  { widthFrac: 0.32, heightFrac: 0.06, targetWidth: 1800, mode: "reflect" },
  { widthFrac: 0.45, heightFrac: 0.09, targetWidth: 1600, mode: "contrast" },
  { widthFrac: 0.45, heightFrac: 0.09, targetWidth: 1600, mode: "invert" },
  { widthFrac: 0.60, heightFrac: 0.12, targetWidth: 1500, mode: "binary" },
  { widthFrac: 0.60, heightFrac: 0.12, targetWidth: 1500, mode: "reflect" },
];

/** Near → mid → far barcode crops (raw + contrast for tough stickers). */
const BARCODE_ZOOM_PRESETS: ScanPreset[] = [
  { widthFrac: 0.92, heightFrac: 0.48, targetWidth: 1400, mode: "raw" },
  { widthFrac: 0.72, heightFrac: 0.36, targetWidth: 1500, mode: "raw" },
  { widthFrac: 0.52, heightFrac: 0.28, targetWidth: 1600, mode: "raw" },
  { widthFrac: 0.36, heightFrac: 0.20, targetWidth: 1700, mode: "raw" },
  { widthFrac: 0.72, heightFrac: 0.36, targetWidth: 1500, mode: "contrast" },
  { widthFrac: 0.52, heightFrac: 0.28, targetWidth: 1600, mode: "reflect" },
  { widthFrac: 0.72, heightFrac: 0.36, targetWidth: 1500, mode: "invert" },
];

const MOTION_SKIP = 18;
const SHARP_OK = 22;
const GLARE_HEAVY = 0.14;
const BARCODE_LOOP_MS = 140;
const OCR_LOOP_MS = 420;
const NATIVE_LOOP_MS = 200;
const BARCODE_FORMAT_VOTES = 2;
const OCR_VOTE_THRESHOLD = 2;

async function enhanceCameraTrack(track: MediaStreamTrack): Promise<void> {
  const caps = track.getCapabilities?.() as
    | {
        focusMode?: string[];
        zoom?: { min: number; max: number };
        exposureMode?: string[];
        whiteBalanceMode?: string[];
        frameRate?: { max: number };
      }
    | undefined;
  if (!caps) return;

  const advanced: Record<string, string | number>[] = [];
  if (caps.focusMode?.includes("continuous")) advanced.push({ focusMode: "continuous" });
  if (caps.exposureMode?.includes("continuous")) advanced.push({ exposureMode: "continuous" });
  if (caps.whiteBalanceMode?.includes("continuous")) advanced.push({ whiteBalanceMode: "continuous" });
  if (caps.zoom && caps.zoom.max > caps.zoom.min) advanced.push({ zoom: caps.zoom.min });
  if (!advanced.length) return;
  try {
    await track.applyConstraints({ advanced } as MediaTrackConstraints);
  } catch {
    // Optional — many browsers reject unsupported advanced constraints.
  }
}

async function setTorch(track: MediaStreamTrack | null, on: boolean): Promise<boolean> {
  if (!track) return false;
  const caps = track.getCapabilities?.() as { torch?: boolean } | undefined;
  if (!caps?.torch) return false;
  try {
    await track.applyConstraints({ advanced: [{ torch: on }] } as unknown as MediaTrackConstraints);
    return true;
  } catch {
    return false;
  }
}

function torchSupported(track: MediaStreamTrack | null): boolean {
  if (!track) return false;
  const caps = track.getCapabilities?.() as { torch?: boolean } | undefined;
  return Boolean(caps?.torch);
}

async function openRearCamera(): Promise<MediaStream> {
  const tryOpen = async (video: boolean | MediaTrackConstraints) => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video });
    const track = stream.getVideoTracks()[0];
    if (track) await enhanceCameraTrack(track);
    return stream;
  };

  // Prefer soft constraints first on mobile — hard 1080p / resizeMode often fails
  // with OverconstrainedError or "Could not start video source".
  const attempts: Array<boolean | MediaTrackConstraints> = [
    { facingMode: { ideal: "environment" } },
    { facingMode: "environment" },
    {
      facingMode: { ideal: "environment" },
      width: { ideal: 1280 },
      height: { ideal: 720 },
    },
    {
      facingMode: { ideal: "environment" },
      width: { ideal: 1920 },
      height: { ideal: 1080 },
      frameRate: { ideal: 30 },
    },
    true,
  ];

  let primaryErr: unknown = null;
  for (const constraints of attempts) {
    try {
      return await tryOpen(constraints);
    } catch (err) {
      primaryErr = err;
    }
  }

  const { BrowserCodeReader } = await loadZxing();
  const devices = await BrowserCodeReader.listVideoInputDevices().catch(() => []);
  if (devices.length) {
    const preferred =
      devices.find((d) => /back|rear|environment|wide/i.test(d.label)) ??
      devices[devices.length - 1];
    try {
      return await tryOpen({ deviceId: { exact: preferred.deviceId } });
    } catch (err) {
      primaryErr = err;
    }
    for (const device of devices) {
      if (device.deviceId === preferred.deviceId) continue;
      try {
        return await tryOpen({ deviceId: { exact: device.deviceId } });
      } catch (err) {
        primaryErr = err;
      }
    }
  }

  throw primaryErr ?? new Error("Camera access failed");
}

function buildGrayHistogram(grays: Uint8Array): number[] {
  const hist = new Array<number>(256).fill(0);
  for (let i = 0; i < grays.length; i++) hist[grays[i]] += 1;
  return hist;
}

function percentileFromHist(hist: number[], total: number, pct: number): number {
  const target = Math.floor(total * pct);
  let acc = 0;
  for (let t = 0; t < 256; t++) {
    acc += hist[t];
    if (acc >= target) return t;
  }
  return 255;
}

function otsuThreshold(hist: number[], total: number): number {
  let sum = 0;
  for (let t = 0; t < 256; t++) sum += t * hist[t];
  let sumB = 0;
  let wB = 0;
  let maxVar = 0;
  let threshold = 128;
  for (let t = 0; t < 256; t++) {
    wB += hist[t];
    if (!wB) continue;
    const wF = total - wB;
    if (!wF) break;
    sumB += t * hist[t];
    const mB = sumB / wB;
    const mF = (sum - sumB) / wF;
    const variance = wB * wF * (mB - mF) * (mB - mF);
    if (variance > maxVar) {
      maxVar = variance;
      threshold = t;
    }
  }
  return threshold;
}

/** Laplacian variance — higher = sharper (detects blur / shake smear). */
function laplacianVariance(gray: Uint8Array, w: number, h: number): number {
  if (w < 3 || h < 3) return 0;
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const lap =
        gray[i - w] + gray[i + w] + gray[i - 1] + gray[i + 1] - 4 * gray[i];
      sum += lap;
      sumSq += lap * lap;
      n += 1;
    }
  }
  if (!n) return 0;
  const mean = sum / n;
  return sumSq / n - mean * mean;
}

function meanAbsDiff(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  if (!n) return 0;
  let sum = 0;
  // Subsample for speed.
  for (let i = 0; i < n; i += 4) sum += Math.abs(a[i] - b[i]);
  return (sum / (n / 4)) ;
}

/** Light box blur — knocks down dust speckles before OCR. */
function boxBlur3(gray: Uint8Array, w: number, h: number): Uint8Array {
  const out = new Uint8Array(gray.length);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let sum = 0;
      let count = 0;
      for (let dy = -1; dy <= 1; dy++) {
        const yy = y + dy;
        if (yy < 0 || yy >= h) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const xx = x + dx;
          if (xx < 0 || xx >= w) continue;
          sum += gray[yy * w + xx];
          count += 1;
        }
      }
      out[y * w + x] = Math.round(sum / count);
    }
  }
  return out;
}

/** Unsharp mask to recover soft / slightly out-of-focus lettering. */
function unsharpMask(gray: Uint8Array, w: number, h: number, amount = 1.35): Uint8Array {
  const blur = boxBlur3(gray, w, h);
  const out = new Uint8Array(gray.length);
  for (let i = 0; i < gray.length; i++) {
    const v = gray[i] + amount * (gray[i] - blur[i]);
    out[i] = Math.max(0, Math.min(255, Math.round(v)));
  }
  return out;
}

function writeGrayToImageData(data: Uint8ClampedArray, gray: Uint8Array): void {
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    data[i] = gray[p];
    data[i + 1] = gray[p];
    data[i + 2] = gray[p];
  }
}

function cropRect(video: HTMLVideoElement, widthFrac: number, heightFrac: number) {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  const bandW = Math.max(32, Math.floor(vw * widthFrac));
  const bandH = Math.max(16, Math.floor(vh * heightFrac));
  return {
    vw,
    vh,
    bandW,
    bandH,
    bandX: Math.floor((vw - bandW) / 2),
    bandY: Math.floor((vh - bandH) / 2),
  };
}

/** Small center probe for blur / shake / glass-glare gating. */
function captureProbe(
  video: HTMLVideoElement,
): { gray: Uint8Array; w: number; h: number } | null {
  const rect = cropRect(video, 0.7, 0.2);
  if (!rect.vw || !rect.vh) return null;
  const w = 320;
  const h = Math.max(24, Math.round((rect.bandH / rect.bandW) * w));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(video, rect.bandX, rect.bandY, rect.bandW, rect.bandH, 0, 0, w, h);
  const image = ctx.getImageData(0, 0, w, h);
  const gray = new Uint8Array(w * h);
  for (let i = 0, p = 0; i < image.data.length; i += 4, p++) {
    // min-RGB damps specular glass reflections in the probe too.
    gray[p] = Math.min(image.data[i], image.data[i + 1], image.data[i + 2]);
  }
  return { gray, w, h };
}

function assessFrameQuality(
  probe: { gray: Uint8Array; w: number; h: number },
  prevGray: Uint8Array | null,
): FrameQuality {
  const sharpness = laplacianVariance(probe.gray, probe.w, probe.h);
  const motion = prevGray && prevGray.length === probe.gray.length
    ? meanAbsDiff(prevGray, probe.gray)
    : 0;
  let hot = 0;
  for (let i = 0; i < probe.gray.length; i++) if (probe.gray[i] >= 245) hot += 1;
  const glareRatio = hot / probe.gray.length;
  return {
    sharpness,
    motion,
    glareRatio,
    stable: motion < MOTION_SKIP,
    sharpEnough: sharpness >= SHARP_OK,
    glareHeavy: glareRatio >= GLARE_HEAVY,
  };
}

function pickPresetsForQuality(
  base: ScanPreset[],
  quality: FrameQuality,
  index: number,
): ScanPreset {
  // Prefer reflection-suppression on glass; sharpen when soft/blurry.
  let preferred = base;
  if (quality.glareHeavy) {
    preferred = [...base].sort((a, b) => Number(b.mode === "reflect") - Number(a.mode === "reflect"));
  } else if (!quality.sharpEnough) {
    preferred = [...base].sort((a, b) => Number(b.mode === "sharpen") - Number(a.mode === "sharpen"));
  }
  return preferred[index % preferred.length];
}

/**
 * Center-crop + upscale with condition-aware preprocessing:
 * blur sharpening, glass-reflection suppress, dust denoise, binary/invert.
 */
function captureScanBand(
  video: HTMLVideoElement,
  preset: ScanPreset,
  fuseGray?: Uint8Array | null,
): HTMLCanvasElement | null {
  const rect = cropRect(video, preset.widthFrac, preset.heightFrac);
  if (!rect.vw || !rect.vh) return null;

  const scale = Math.max(1.5, preset.targetWidth / rect.bandW);
  const canvas = document.createElement("canvas");
  canvas.width = Math.floor(rect.bandW * scale);
  canvas.height = Math.floor(rect.bandH * scale);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;

  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(
    video,
    rect.bandX,
    rect.bandY,
    rect.bandW,
    rect.bandH,
    0,
    0,
    canvas.width,
    canvas.height,
  );

  if (preset.mode === "raw") return canvas;

  const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = image.data;
  const w = canvas.width;
  const h = canvas.height;
  let gray = new Uint8Array(w * h);

  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    if (preset.mode === "reflect") {
      // Specular windshield/dash glare is usually bright in all channels — take min.
      gray[p] = Math.min(data[i], data[i + 1], data[i + 2]);
    } else {
      gray[p] = Math.round(data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114);
    }
  }

  // Temporal fuse (stable frames) reduces shake noise and dust flicker.
  if (fuseGray && fuseGray.length === gray.length) {
    const fused = new Uint8Array(gray.length);
    for (let i = 0; i < gray.length; i++) {
      fused[i] = Math.round(fuseGray[i] * 0.45 + gray[i] * 0.55);
    }
    gray = fused;
  }

  // Soft denoise before threshold/sharpen (dust / sensor noise).
  gray = new Uint8Array(boxBlur3(gray, w, h));

  if (preset.mode === "sharpen" || preset.mode === "contrast" || preset.mode === "reflect") {
    if (preset.mode === "sharpen") gray = new Uint8Array(unsharpMask(gray, w, h, 1.5));
    const hist = buildGrayHistogram(gray);
    const lo = percentileFromHist(hist, gray.length, 0.04);
    const hi = percentileFromHist(hist, gray.length, 0.96);
    // Crush extreme specular highlights from glass.
    const glareCeil = percentileFromHist(hist, gray.length, 0.92);
    const span = Math.max(1, hi - lo);
    const out = new Uint8Array(gray.length);
    for (let i = 0; i < gray.length; i++) {
      const clipped = Math.min(gray[i], glareCeil + 8);
      out[i] = Math.max(0, Math.min(255, ((clipped - lo) / span) * 255));
    }
    writeGrayToImageData(data, out);
  } else {
    const hist = buildGrayHistogram(gray);
    const threshold = otsuThreshold(hist, gray.length);
    const invert = preset.mode === "invert";
    const out = new Uint8Array(gray.length);
    for (let i = 0; i < gray.length; i++) {
      let v = gray[i] < threshold ? 0 : 255;
      if (invert) v = 255 - v;
      out[i] = v;
    }
    writeGrayToImageData(data, out);
  }

  ctx.putImageData(image, 0, 0);
  return canvas;
}

/** Keep last stable gray for temporal fusion. */
function extractGrayFromCanvas(canvas: HTMLCanvasElement): Uint8Array | null {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const gray = new Uint8Array(canvas.width * canvas.height);
  for (let i = 0, p = 0; i < image.data.length; i += 4, p++) {
    gray[p] = image.data[i];
  }
  return gray;
}

async function createOcrWorker(): Promise<OcrWorker> {
  const { createWorker, PSM } = await import("tesseract.js");
  const worker = await createWorker("eng", 1);
  await worker.setParameters({
    tessedit_char_whitelist: VIN_CHAR_WHITELIST,
    tessedit_pageseg_mode: PSM.SINGLE_LINE,
    user_defined_dpi: "300",
    preserve_interword_spaces: "1",
  });
  return worker as unknown as OcrWorker;
}

async function setOcrPageSeg(worker: OcrWorker, sparse: boolean): Promise<void> {
  try {
    const { PSM } = await import("tesseract.js");
    await worker.setParameters({
      tessedit_pageseg_mode: sparse ? PSM.SPARSE_TEXT : PSM.SINGLE_LINE,
    });
  } catch {
    // Optional — keep previous page-seg mode.
  }
}

function tryDecodeBarcodeCanvas(
  reader: ZxingReader,
  canvas: HTMLCanvasElement,
): string | null {
  try {
    return reader.decodeFromCanvas(canvas).getText();
  } catch {
    return null;
  }
}

function createNativeBarcodeDetector(): { detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>> } | null {
  const Detector = (window as unknown as { BarcodeDetector?: new (opts: { formats: string[] }) => { detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>> } }).BarcodeDetector;
  if (!Detector) return null;
  try {
    return new Detector({ formats: [...NATIVE_BARCODE_FORMATS] });
  } catch {
    return null;
  }
}

export function VinInput({ value, onChange, status, looking, required = true }: VinInputProps) {
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanHint, setScanHint] = useState("Starting camera…");
  const [torchOn, setTorchOn] = useState(false);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  /** Client-only: portal scan UI past overflow-hidden dashboard shells. */
  const [portalReady, setPortalReady] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const controlsRef = useRef<ScannerControls | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  /** Opened from Scan click (user gesture) — required on iOS/Android WebKit. */
  const pendingStreamRef = useRef<MediaStream | null>(null);
  /** When startScanner already failed, effect must not re-prompt getUserMedia. */
  const cameraOpenFailedRef = useRef(false);
  const ocrWorkerRef = useRef<OcrWorker | null>(null);
  const captureHandlerRef = useRef<(() => Promise<void>) | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useEffect(() => {
    if (!scanning) return;

    let cancelled = false;
    let ocrTimer: number | null = null;
    let barcodeTimer: number | null = null;
    let nativeTimer: number | null = null;
    let settled = false;
    let nearIndex = 0;
    let farIndex = 0;
    let barcodeIndex = 0;
    let ocrTick = 0;
    let busyBarcode = false;
    let busyOcr = false;
    let prevProbeGray: Uint8Array | null = null;
    let fuseGray: Uint8Array | null = null;
    const ocrVotes = new Map<string, number>();
    const barcodeVotes = new Map<string, number>();
    let liveReader: ZxingReader | null = null;
    let zoomReader: ZxingReader | null = null;

    const stopEverything = () => {
      if (ocrTimer !== null) {
        window.clearTimeout(ocrTimer);
        ocrTimer = null;
      }
      if (barcodeTimer !== null) {
        window.clearTimeout(barcodeTimer);
        barcodeTimer = null;
      }
      if (nativeTimer !== null) {
        window.clearInterval(nativeTimer);
        nativeTimer = null;
      }
      captureHandlerRef.current = null;
      const track = streamRef.current?.getVideoTracks()[0] ?? null;
      void setTorch(track, false);
      controlsRef.current?.stop();
      controlsRef.current = null;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      releaseZxingStreams();
      const worker = ocrWorkerRef.current;
      ocrWorkerRef.current = null;
      void worker?.terminate();
    };

    const acceptVin = (vin: string) => {
      if (cancelled || settled) return;
      settled = true;
      stopEverything();
      onChangeRef.current(vin);
      setScanning(false);
      setCapturing(false);
      setCameraReady(false);
      setTorchOn(false);
      setTorchAvailable(false);
      setScanHint(`Scanned ${vin}`);
    };

    const acceptBarcodeVin = (raw: string) => {
      const vin = extractVin(raw);
      if (!vin || cancelled || settled) return false;
      if (hasValidVinCheckDigit(vin)) {
        acceptVin(vin);
        return true;
      }
      // Format-only barcodes need two agreeing reads (door-jamb CODE_39 can glitch).
      const votes = (barcodeVotes.get(vin) ?? 0) + 1;
      barcodeVotes.set(vin, votes);
      if (votes >= BARCODE_FORMAT_VOTES) {
        acceptVin(vin);
        return true;
      }
      setScanHint(`Barcode ${vin.slice(0, 8)}… hold steady to confirm`);
      return false;
    };

    const noteOcrCandidate = (vin: string) => {
      const votes = (ocrVotes.get(vin) ?? 0) + 1;
      ocrVotes.set(vin, votes);
      if (votes >= OCR_VOTE_THRESHOLD) {
        acceptVin(vin);
        return true;
      }
      setScanHint(`Confirming ${vin.slice(0, 8)}… hold steady`);
      return false;
    };

    const recognizePreset = async (
      worker: OcrWorker,
      video: HTMLVideoElement,
      preset: ScanPreset,
    ): Promise<boolean> => {
      const band = captureScanBand(video, preset, fuseGray);
      if (!band) return false;
      if (preset.mode !== "raw") {
        const g = extractGrayFromCanvas(band);
        if (g) fuseGray = g;
      }
      const { data } = await worker.recognize(band);
      const vin = extractVinFromOcr(data.text);
      return Boolean(vin && noteOcrCandidate(vin));
    };

    const scanBarcodeCrops = (video: HTMLVideoElement, passes: number): boolean => {
      if (!zoomReader) return false;
      for (let i = 0; i < passes; i++) {
        const preset = BARCODE_ZOOM_PRESETS[barcodeIndex % BARCODE_ZOOM_PRESETS.length];
        barcodeIndex += 1;
        const crop = captureScanBand(video, preset, null);
        if (!crop) continue;
        const text = tryDecodeBarcodeCanvas(zoomReader, crop);
        if (text && acceptBarcodeVin(text)) return true;
        if (settled) return true;
      }
      return false;
    };

    (async () => {
      setScanHint("Starting camera…");
      setTorchOn(false);
      setTorchAvailable(false);
      setCapturing(false);
      setCameraReady(false);

      // Prefer stream opened from Scan click (user gesture). Fallback reopen covers
      // React Strict Mode remount after permission was already granted.
      let stream = pendingStreamRef.current;
      pendingStreamRef.current = null;
      const streamDead =
        !stream || stream.getVideoTracks().every((t) => t.readyState === "ended");
      if (streamDead) {
        if (stream) stream.getTracks().forEach((t) => t.stop());
        if (cameraOpenFailedRef.current) {
          cameraOpenFailedRef.current = false;
          return;
        }
        try {
          stream = await openRearCamera();
        } catch (err) {
          if (!cancelled) setScanError(cameraErrorMessage(err));
          return;
        }
      }
      if (!stream) {
        if (!cancelled) setScanError("Camera could not be started. Type the VIN instead.");
        return;
      }
      if (cancelled) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }

      const video = await waitForVideoElement(() => videoRef.current, () => cancelled);
      if (cancelled) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      if (!video) {
        stream.getTracks().forEach((t) => t.stop());
        setScanError("Camera preview failed to load. Close and try again, or type the VIN.");
        return;
      }

      try {
        streamRef.current = stream;
        const track = stream.getVideoTracks()[0] ?? null;
        setTorchAvailable(torchSupported(track));
        await attachStreamToVideo(video, stream);

        const ready = await waitForVideoReady(video, () => cancelled);
        if (cancelled) return;
        if (!ready) {
          setScanError("Camera preview has no video frames. Close and try again.");
          stopEverything();
          return;
        }
        setCameraReady(true);
        setScanHint("Point at the VIN barcode or printed VIN — keep inside the box");

        try {
          [liveReader, zoomReader] = await Promise.all([
            createVinReader(false),
            createVinReader(true),
          ]);
        } catch {
          // Native + OCR paths still work without ZXing.
        }
        if (cancelled) return;

        // 1) Live ZXing stream (full-frame backup; ROI canvas is primary).
        try {
          if (liveReader) {
            controlsRef.current = await liveReader.decodeFromStream(stream, video, (result) => {
              if (!result || cancelled || settled) return;
              acceptBarcodeVin(result.getText());
            });
          }
        } catch {
          // Canvas + native paths still work without live stream decode.
        }

        // 2) Native BarcodeDetector (Chrome/Android fast path)
        const nativeDetector = createNativeBarcodeDetector();
        if (nativeDetector) {
          nativeTimer = window.setInterval(() => {
            if (cancelled || settled || busyBarcode) return;
            void nativeDetector
              .detect(video)
              .then((codes) => {
                for (const code of codes) {
                  acceptBarcodeVin(code.rawValue);
                  if (settled) return;
                }
              })
              .catch(() => undefined);
          }, NATIVE_LOOP_MS);
        }

        // 3) ROI barcode canvas loop — primary path for door-jamb stickers.
        const runBarcode = () => {
          if (cancelled || settled) return;
          if (!busyOcr && !busyBarcode && video.videoWidth > 0) {
            busyBarcode = true;
            try {
              scanBarcodeCrops(video, 2);
            } finally {
              busyBarcode = false;
            }
          }
          if (!cancelled && !settled) {
            barcodeTimer = window.setTimeout(runBarcode, BARCODE_LOOP_MS);
          }
        };
        barcodeTimer = window.setTimeout(runBarcode, 120);

        // 4) Manual capture — multi-pass barcode + OCR on one frozen effort burst.
        captureHandlerRef.current = async () => {
          if (cancelled || settled || busyOcr) return;
          setCapturing(true);
          setScanHint("Capturing… hold still");
          busyOcr = true;
          try {
            if (scanBarcodeCrops(video, BARCODE_ZOOM_PRESETS.length)) return;
            const worker = ocrWorkerRef.current;
            if (!worker) {
              setScanHint("No VIN yet — try closer to the barcode, or type it.");
              return;
            }
            const probe = captureProbe(video);
            const q = probe
              ? assessFrameQuality(probe, prevProbeGray)
              : {
                  sharpness: 0,
                  motion: 0,
                  glareRatio: 0,
                  stable: true,
                  sharpEnough: true,
                  glareHeavy: false,
                };
            await setOcrPageSeg(worker, false);
            for (let i = 0; i < NEAR_OCR_PRESETS.length; i++) {
              if (cancelled || settled) return;
              const preset = pickPresetsForQuality(NEAR_OCR_PRESETS, q, i);
              if (await recognizePreset(worker, video, preset)) return;
            }
            await setOcrPageSeg(worker, true);
            for (let i = 0; i < FAR_OCR_PRESETS.length; i++) {
              if (cancelled || settled) return;
              const preset = pickPresetsForQuality(FAR_OCR_PRESETS, q, i);
              if (await recognizePreset(worker, video, preset)) return;
            }
            setScanHint("Couldn’t read that frame — tilt to cut glare, move closer, try again.");
          } finally {
            busyOcr = false;
            setCapturing(false);
          }
        };

        // 5) OCR for printed / windshield VIN (secondary; slower than barcode).
        try {
          const worker = await createOcrWorker();
          if (cancelled || settled) {
            await worker.terminate();
            return;
          }
          ocrWorkerRef.current = worker;
          setScanHint("Aim at barcode (fastest) or printed VIN…");

          const scheduleOcr = (delay = OCR_LOOP_MS) => {
            if (cancelled || settled) return;
            ocrTimer = window.setTimeout(() => {
              void runOcr();
            }, delay);
          };

          const runOcr = async () => {
            if (cancelled || settled) return;
            ocrTick += 1;
            if (busyBarcode || busyOcr) {
              scheduleOcr(OCR_LOOP_MS);
              return;
            }
            busyOcr = true;
            try {
              const probe = captureProbe(video);
              let quality: FrameQuality | null = null;
              if (probe) {
                quality = assessFrameQuality(probe, prevProbeGray);
                prevProbeGray = probe.gray;

                if (!quality.stable) {
                  fuseGray = null;
                  setScanHint("Too shaky — hold still, or tap Capture");
                  // Skip most shaky frames but keep the loop alive.
                  if (ocrTick % 2 !== 0) return;
                } else if (!quality.sharpEnough) {
                  setScanHint("Focusing… hold steady or tap Capture");
                } else if (quality.glareHeavy) {
                  setScanHint("Glare — tilt phone or tap Light, then Capture");
                } else {
                  setScanHint("Reading printed VIN… barcode is faster if available");
                }
              }

              const q = quality ?? {
                sharpness: 0,
                motion: 0,
                glareRatio: 0,
                stable: true,
                sharpEnough: true,
                glareHeavy: false,
              };

              await setOcrPageSeg(worker, ocrTick % 3 === 0);
              const nearPreset = pickPresetsForQuality(NEAR_OCR_PRESETS, q, nearIndex);
              nearIndex += 1;
              if (await recognizePreset(worker, video, nearPreset)) return;

              if (cancelled || settled) return;
              // Far OCR every other tick to keep CPU free for barcode.
              if (ocrTick % 2 === 0) {
                const farPreset = pickPresetsForQuality(FAR_OCR_PRESETS, q, farIndex);
                farIndex += 1;
                if (await recognizePreset(worker, video, farPreset)) return;
              }
            } catch {
              // Keep scanning; OCR can miss frames.
            } finally {
              busyOcr = false;
              scheduleOcr(OCR_LOOP_MS);
            }
          };
          ocrTimer = window.setTimeout(() => {
            void runOcr();
          }, 350);
        } catch {
          setScanHint("Barcode scan active. Aim at the VIN barcode, or tap Capture.");
        }
      } catch (err) {
        if (cancelled) return;
        stopEverything();
        setScanError(cameraErrorMessage(err));
      }
    })();

    return () => {
      cancelled = true;
      // If effect cleans up before attaching, release the pending stream too.
      const pending = pendingStreamRef.current;
      pendingStreamRef.current = null;
      pending?.getTracks().forEach((t) => t.stop());
      stopEverything();
    };
  }, [scanning]);

  async function startScanner() {
    if (scanning) return;
    setScanError(null);
    setScanHint("Starting camera…");
    setTorchOn(false);
    setTorchAvailable(false);
    setCapturing(false);
    setCameraReady(false);
    cameraOpenFailedRef.current = false;

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      cameraOpenFailedRef.current = true;
      setScanError("Camera not supported in this browser. Type the VIN manually instead.");
      setScanning(true);
      return;
    }
    if (!window.isSecureContext) {
      cameraOpenFailedRef.current = true;
      setScanError(
        "Camera needs HTTPS (or localhost). Open this page over a secure connection, or type the VIN.",
      );
      setScanning(true);
      return;
    }

    try {
      // Keep getUserMedia on the Scan tap call stack — mobile WebKit requires it.
      const stream = await openRearCamera();
      pendingStreamRef.current = stream;
      setScanning(true);
    } catch (err) {
      pendingStreamRef.current = null;
      cameraOpenFailedRef.current = true;
      setScanError(cameraErrorMessage(err));
      setScanning(true);
    }
  }

  async function toggleTorch() {
    const track = streamRef.current?.getVideoTracks()[0] ?? null;
    const next = !torchOn;
    const ok = await setTorch(track, next);
    if (ok) setTorchOn(next);
  }

  async function captureNow() {
    const handler = captureHandlerRef.current;
    if (!handler || capturing) return;
    await handler();
  }

  function closeScanner() {
    const track = streamRef.current?.getVideoTracks()[0] ?? null;
    void setTorch(track, false);
    controlsRef.current?.stop();
    controlsRef.current = null;
    captureHandlerRef.current = null;
    pendingStreamRef.current?.getTracks().forEach((t) => t.stop());
    pendingStreamRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    releaseZxingStreams();
    const worker = ocrWorkerRef.current;
    ocrWorkerRef.current = null;
    void worker?.terminate();
    setScanning(false);
    setScanError(null);
    setCapturing(false);
    setCameraReady(false);
    setTorchOn(false);
    setTorchAvailable(false);
  }

  const vinLen = Math.min(value.replace(/[\s-]/g, "").length, 17);
  const vinComplete = vinLen === 17;
  const scanBusy = cameraReady && !scanError && !capturing;
  const statusTone = scanError
    ? "error"
    : /glare|tilt|light/i.test(scanHint)
      ? "warn"
      : /confirm|barcode|scanned|reading|captur/i.test(scanHint)
        ? "active"
        : "idle";

  return (
    <div className="space-y-2 sm:col-span-2 lg:col-span-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
          VIN{required ? "" : " · optional"}
        </span>
        <span
          className={`font-mono text-[11px] tabular-nums tracking-wider ${
            vinComplete ? "text-[var(--accent)]" : "text-[var(--muted)]"
          }`}
        >
          {vinLen}
          <span className="text-[var(--muted)]">/17</span>
        </span>
      </div>

      <div className="flex flex-row items-stretch gap-2">
        <div className="relative min-w-0 flex-1">
          <input
            value={value}
            required={required}
            maxLength={17}
            autoComplete="off"
            spellCheck={false}
            inputMode="text"
            placeholder={required ? "17-character VIN" : "Scan if available, or skip"}
            onChange={(e) => onChange(e.target.value.toUpperCase())}
            className="w-full rounded-xl border border-[var(--line)] bg-white px-3.5 py-2.5 font-mono text-sm uppercase tracking-[0.12em] outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-glow)]"
          />
          {vinComplete ? (
            <span
              className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[var(--accent)]"
              aria-hidden
            >
              <CheckIcon />
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => {
            void startScanner();
          }}
          className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-white shadow-[0_10px_28px_-14px_rgba(240,90,36,0.75)] transition hover:bg-[var(--accent-hover)]"
        >
          <ScanIcon />
          Scan
        </button>
      </div>

      <p className="text-xs text-[var(--muted)]">
        {looking ? (
          <span className="inline-flex items-center gap-2">
            <span className="vin-status-dot h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
            Looking up VIN…
          </span>
        ) : (
          status || "Camera scan · door-jamb barcode · or type"
        )}
      </p>

      {/* Portal past overflow-hidden shells so dim covers header + full viewport */}
      {portalReady &&
        scanning &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-end justify-center bg-black/65 p-0 backdrop-blur-[2px] sm:items-center sm:p-5"
            role="dialog"
            aria-modal="true"
            aria-label="Scan VIN"
            onClick={closeScanner}
          >
            <div
              className="flex max-h-[100dvh] w-full max-w-lg flex-col overflow-hidden rounded-t-[1.35rem] border border-white/10 bg-[#0c0c0c] text-white shadow-[0_32px_80px_-24px_rgba(0,0,0,0.85)] sm:max-h-[min(92dvh,720px)] sm:rounded-[1.35rem]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="relative flex items-center justify-between gap-3 px-4 pb-2 pt-4 sm:px-5">
                <div className="min-w-0">
                  <p className="font-display text-lg font-semibold tracking-tight">Scan VIN</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {torchAvailable && (
                    <button
                      type="button"
                      onClick={() => {
                        void toggleTorch();
                      }}
                      className={`inline-flex h-10 w-10 items-center justify-center rounded-full border transition ${
                        torchOn
                          ? "border-[var(--accent)] bg-[var(--accent)] text-white"
                          : "border-white/15 bg-white/5 text-white/85 hover:bg-white/10"
                      }`}
                      aria-pressed={torchOn}
                      aria-label={torchOn ? "Turn light off" : "Turn light on"}
                    >
                      <TorchIcon on={torchOn} />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={closeScanner}
                    className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15 bg-white/5 text-white/85 transition hover:bg-white/10"
                    aria-label="Close scanner"
                  >
                    <CloseIcon />
                  </button>
                </div>
              </div>

              <div className="relative mx-3 overflow-hidden rounded-2xl bg-black ring-1 ring-white/10 sm:mx-4">
                <video
                  ref={videoRef}
                  className="aspect-[4/3] w-full bg-black object-cover"
                  muted
                  playsInline
                  autoPlay
                />
                {/* Guide matches barcode + near OCR center band. */}
                <div className="pointer-events-none absolute inset-0">
                  <div className="absolute inset-x-0 top-0 h-[34%] bg-gradient-to-b from-black/70 via-black/45 to-transparent" />
                  <div className="absolute inset-x-0 bottom-0 h-[34%] bg-gradient-to-t from-black/70 via-black/45 to-transparent" />
                  <div className="absolute inset-y-[34%] left-0 w-[4%] bg-black/40" />
                  <div className="absolute inset-y-[34%] right-0 w-[4%] bg-black/40" />

                  <div
                    className={`vin-reticle-glow absolute inset-x-[4%] top-[34%] h-[32%] rounded-xl border border-[var(--accent)]/70 ${
                      scanBusy ? "" : "opacity-70"
                    }`}
                  >
                    <span className="absolute -left-px -top-px h-5 w-5 rounded-tl-xl border-l-[3px] border-t-[3px] border-white" />
                    <span className="absolute -right-px -top-px h-5 w-5 rounded-tr-xl border-r-[3px] border-t-[3px] border-white" />
                    <span className="absolute -bottom-px -left-px h-5 w-5 rounded-bl-xl border-b-[3px] border-l-[3px] border-white" />
                    <span className="absolute -bottom-px -right-px h-5 w-5 rounded-br-xl border-b-[3px] border-r-[3px] border-white" />
                    {scanBusy ? (
                      <span className="vin-scan-beam absolute inset-x-3 h-px bg-gradient-to-r from-transparent via-[var(--accent)] to-transparent shadow-[0_0_12px_2px_rgba(240,90,36,0.55)]" />
                    ) : null}
                  </div>

                  <p className="absolute inset-x-0 bottom-[22%] text-center text-[11px] font-medium tracking-[0.14em] text-white/80 uppercase">
                    Align barcode or VIN
                  </p>
                </div>

                {!cameraReady && !scanError ? (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/55 backdrop-blur-[1px]">
                    <div className="flex flex-col items-center gap-3">
                      <span className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-[var(--accent)]" />
                      <p className="text-xs font-medium tracking-wide text-white/70">
                        Opening camera…
                      </p>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="flex flex-col gap-3 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 sm:px-5 sm:pb-5">
                <div
                  className={`flex min-h-[2.5rem] items-start gap-2.5 rounded-xl px-3 py-2.5 text-sm leading-snug ${
                    statusTone === "error"
                      ? "bg-red-500/15 text-red-200 ring-1 ring-red-400/30"
                      : statusTone === "warn"
                        ? "bg-amber-500/12 text-amber-100 ring-1 ring-amber-400/25"
                        : "bg-white/[0.06] text-white/75 ring-1 ring-white/10"
                  }`}
                >
                  {!scanError ? (
                    <span
                      className={`vin-status-dot mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                        statusTone === "warn"
                          ? "bg-amber-300"
                          : statusTone === "active"
                            ? "bg-[var(--accent)]"
                            : "bg-white/50"
                      }`}
                      aria-hidden
                    />
                  ) : null}
                  <p className="min-w-0 flex-1">{scanError ?? scanHint}</p>
                </div>

                <div className="flex flex-col items-center">
                  <button
                    type="button"
                    disabled={!cameraReady || capturing || Boolean(scanError)}
                    onClick={() => {
                      void captureNow();
                    }}
                    className="group relative inline-flex h-[4.25rem] w-[4.25rem] items-center justify-center rounded-full bg-gradient-to-b from-white/20 to-white/5 p-[3px] shadow-[0_12px_40px_-12px_rgba(240,90,36,0.65)] transition enabled:hover:scale-[1.03] enabled:active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label={capturing ? "Reading frame" : "Capture frame"}
                  >
                    <span
                      className={`flex h-full w-full items-center justify-center rounded-full transition ${
                        capturing
                          ? "bg-[var(--accent)] text-white"
                          : "bg-white text-[#0c0c0c] group-hover:bg-[var(--accent)] group-hover:text-white"
                      }`}
                    >
                      {capturing ? (
                        <span className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                      ) : (
                        <CaptureIcon />
                      )}
                    </span>
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

function ScanIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 7V5a1 1 0 0 1 1-1h2M20 7V5a1 1 0 0 0-1-1h-2M4 17v2a1 1 0 0 0 1 1h2M20 17v2a1 1 0 0 1-1 1h-2M3 12h18"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 12.5 10 17.5 19 6.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 6l12 12M18 6 6 18"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
      />
    </svg>
  );
}

function TorchIcon({ on }: { on: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9 2h6l1 5H8l1-5ZM9 7h6v3.2c0 .8.3 1.5.9 2.1L18 14.5V22H6v-7.5l2.1-2.2c.6-.6.9-1.3.9-2.1V7Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        fill={on ? "currentColor" : "none"}
        fillOpacity={on ? 0.25 : 0}
      />
      <path d="M12 14.5v3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function CaptureIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 8V6a2 2 0 0 1 2-2h2M20 8V6a2 2 0 0 0-2-2h-2M4 16v2a2 2 0 0 0 2 2h2M20 16v2a2 2 0 0 1-2 2h-2"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
      />
      <circle cx="12" cy="12" r="3.25" stroke="currentColor" strokeWidth="1.85" />
    </svg>
  );
}
