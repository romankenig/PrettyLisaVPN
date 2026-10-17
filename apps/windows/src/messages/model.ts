export type MessageAction = {
  readonly type: "OPEN_SUBSCRIPTION" | "OPEN_SETTINGS" | "OPEN_ABOUT";
  readonly label: string;
};
export type MessageBlock =
  | { readonly type: "paragraph"; readonly text: string }
  | { readonly type: "list"; readonly items: readonly string[] };
export interface AccountMessage {
  readonly id: string;
  readonly revision: number;
  readonly kind: "announcement" | "update" | "promotion";
  readonly title: string;
  readonly blocks: readonly MessageBlock[];
  readonly primary_action: MessageAction | null;
  readonly dismiss_label: string;
  readonly expires_at: string | null;
}
export interface MessageContext {
  readonly platform: "WINDOWS";
  readonly app_version: string;
  readonly locale: string;
  readonly schema_version: 1;
}
export interface MessagesClient {
  list(token: string, context: MessageContext, signal: AbortSignal): Promise<readonly AccountMessage[]>;
  acknowledge(token: string, message: AccountMessage, signal: AbortSignal): Promise<void>;
}
export class MessagesError extends Error {
  constructor(readonly code: "UNSUPPORTED" | "AUTH_INVALID" | "UNAVAILABLE" | "INVALID_RESPONSE") {
    super(code);
    this.name = "MessagesError";
  }
}
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown, limit: number): value is string =>
  typeof value === "string" && value.trim().length > 0 && value.length <= limit;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const iso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
export const messageKey = (message: AccountMessage) => `${message.id}:${message.revision}`;
export const messageExpired = (message: AccountMessage) =>
  message.expires_at !== null && Date.parse(message.expires_at) <= Date.now();

export function parseMessages(value: unknown): readonly AccountMessage[] {
  const invalid = () => { throw new MessagesError("INVALID_RESPONSE"); };
  if (!record(value) || value.schema_version !== 1 || !Array.isArray(value.messages) || value.messages.length > 10) return invalid();
  const keys = new Set<string>();
  return value.messages.map((raw): AccountMessage => {
    if (!record(raw) || !text(raw.id, 36) || !uuid.test(raw.id) ||
      !Number.isSafeInteger(raw.revision) || Number(raw.revision) < 1 ||
      !text(raw.title, 120) || !text(raw.fallback_text, 4000) ||
      !text(raw.dismiss_label, 60) || !Array.isArray(raw.blocks) ||
      raw.blocks.length === 0 || raw.blocks.length > 12 ||
      !(raw.expires_at === null || (typeof raw.expires_at === "string" && iso.test(raw.expires_at) && Number.isFinite(Date.parse(raw.expires_at))))) return invalid();
    let fallback = false;
    const blocks: MessageBlock[] = raw.blocks.map((block) => {
      if (!record(block) || typeof block.type !== "string") return invalid();
      if (block.type === "paragraph") {
        if (!text(block.text, 3000)) return invalid();
        return { type: "paragraph", text: block.text };
      }
      if (block.type === "list") {
        if (!Array.isArray(block.items) || block.items.length === 0 || block.items.length > 12 || !block.items.every((item) => text(item, 500))) return invalid();
        return { type: "list", items: block.items as string[] };
      }
      fallback = true;
      return { type: "paragraph", text: raw.fallback_text as string };
    });
    let action: MessageAction | null = null;
    if (raw.primary_action !== null && raw.primary_action !== undefined) {
      if (!record(raw.primary_action) || !text(raw.primary_action.type, 80)) return invalid();
      const candidate = raw.primary_action;
      if (candidate.type === "OPEN_SUBSCRIPTION" || candidate.type === "OPEN_SETTINGS" || candidate.type === "OPEN_ABOUT") {
        if (!text(candidate.label, 60)) return invalid();
        action = { type: candidate.type, label: candidate.label };
      }
    }
    const message: AccountMessage = {
      id: raw.id.toLowerCase(),
      revision: Number(raw.revision),
      kind: raw.kind === "update" || raw.kind === "promotion" ? raw.kind : "announcement",
      title: raw.title,
      blocks: fallback ? [{ type: "paragraph", text: raw.fallback_text }] : blocks,
      primary_action: action,
      dismiss_label: raw.dismiss_label,
      expires_at: raw.expires_at as string | null,
    };
    const key = messageKey(message);
    if (keys.has(key)) return invalid();
    keys.add(key);
    return message;
  });
}

export function validateAcknowledgement(value: unknown, message: AccountMessage) {
  if (!record(value) || value.id !== message.id || value.revision !== message.revision || value.acknowledged !== true)
    throw new MessagesError("INVALID_RESPONSE");
}
