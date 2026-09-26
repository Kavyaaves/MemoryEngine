// TypeScript mirror of the backend HTTP contract (docs/api-contract.md, v1).
// Every api/* module returns these types, so the whole app agrees on the shape of server data.
// Keep this file in sync with the contract — it is the only place these shapes are defined.

/** ISO-8601 timestamp string (UTC). */
export type ISODateString = string;
/** UUID string. */
export type UUID = string;

export const SOURCE_TYPES = ["whatsapp", "instagram", "journal", "document", "image", "audio", "video"] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];
/** `auto` lets the backend detect the type from the uploaded files. */
export type UploadSourceType = SourceType | "auto";
/** The source types the Media page searches. */
export type MediaSourceType = Extract<SourceType, "image" | "audio" | "video">;

// ---------- Auth ----------
export interface RegisterRequest {
  email: string;
  password: string;
  display_name?: string;
}
export interface LoginRequest {
  email: string;
  password: string;
}
export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}
export interface User {
  id: UUID;
  email: string;
  display_name: string | null;
  created_at: ISODateString;
}

// ---------- Uploads / ingestion ----------
export type JobStatus = "queued" | "processing" | "completed" | "failed" | "duplicate";

export interface JobStats {
  total?: number;
  new?: number;
  skipped?: number;
  embedded?: number;
}

export interface Job {
  id: UUID;
  source_id: UUID | null;
  filename: string;
  source_type: UploadSourceType;
  status: JobStatus;
  /** 0..1 */
  progress: number;
  stats: JobStats;
  error: string | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export interface UploadResponse {
  jobs: Job[];
}

export interface Source {
  id: UUID;
  source_type: SourceType;
  name: string;
  memory_count: number;
  created_at: ISODateString;
  last_processed_at: ISODateString | null;
}

// ---------- Search / Evidence ----------
export type SearchMode = "hybrid" | "fts" | "trgm" | "vector";
/** Known values are listed for autocomplete; `string & {}` still accepts paths added later by the backend. */
export type RetrievalPath = "fts" | "trgm" | "vector" | "graph" | "temporal" | "derived" | (string & {});

export interface MediaRef {
  id: UUID;
  kind: string; // "image" | "audio" | "video" | ...
  url: string;
  mime_type: string;
}

/** One retrieved memory, with its provenance. Used by search, ask and the timeline day view. */
export interface Evidence {
  memory_id: UUID;
  source_type: SourceType | (string & {});
  source_name: string;
  conversation_id: UUID | null;
  conversation_title: string | null;
  timestamp: ISODateString | null;
  author: string | null;
  text: string;
  snippet: string;
  language: string;
  script: string;
  score: number;
  retrieval_paths: RetrievalPath[];
  media: MediaRef[];
  /** null: not analysed yet, or nothing to analyse (e.g. a photo without a caption). */
  sentiment?: Sentiment | null;
}

export interface SearchParams {
  q: string;
  /** Inclusive YYYY-MM-DD. */
  start?: string;
  /** Inclusive YYYY-MM-DD. */
  end?: string;
  person_id?: UUID;
  source_type?: SourceType;
  k?: number;
  mode?: SearchMode;
}

export interface SearchResponse {
  results: Evidence[];
  timings_ms: Record<string, number>;
}

// ---------- Photos ----------
// Photos are never analysed: only their name and dates are used. Captions are written by the user.
/** none = no caption · pending = saved, not ingested yet · ingested = searchable. */
export type CaptionStatus = "none" | "pending" | "ingested";
export type CaptionFilter = CaptionStatus | "all";
/** Where the photo's timeline date came from, best first. */
export type PhotoDateSource = "exif_taken" | "filename" | "exif_changed" | "file_modified" | "uploaded";

export interface Photo {
  memory_id: UUID;
  filename: string;
  url: string;
  mime_type: string | null;
  /** The date the photo has in the timeline. */
  timestamp: ISODateString | null;
  date_source: PhotoDateSource;
  taken_at: ISODateString | null;
  changed_at: ISODateString | null;
  file_modified_at: ISODateString | null;
  uploaded_at: ISODateString;
  caption: string;
  caption_status: CaptionStatus;
}

export interface PhotoFilters {
  /** Inclusive YYYY-MM-DD. */
  start?: string;
  /** Inclusive YYYY-MM-DD. */
  end?: string;
  /** Text in the file name or caption. */
  q?: string;
  caption?: CaptionFilter;
}

export interface PhotosResponse {
  photos: Photo[];
  /** Captions saved but not ingested yet, across the whole library. */
  pending_captions: number;
}

export interface CaptionIngestResponse {
  ingested: number;
  embedded: number;
  /** Captions whose sentiment was analysed. */
  sentiment: number;
}

// ---------- Sentiment ----------
// From a local Tamil/Tanglish model (backend app/sentiment/). It only says positive or negative;
// answers it isn't confident about are "neutral".
export type SentimentLabel = "positive" | "negative" | "neutral";

export interface Sentiment {
  label: SentimentLabel;
  /** The model's confidence, 0.5..1. */
  score: number;
}

export interface MoodBucket {
  /** "2024" | "2024-06" | "2024-06-14" */
  period: string;
  positive: number;
  negative: number;
  neutral: number;
  /** (positive − negative) / all analysed: −1 = all negative … +1 = all positive. */
  mood: number;
}
export interface MoodTimelineResponse {
  buckets: MoodBucket[];
}
export interface MoodTimelineParams {
  granularity: Granularity;
  start?: string;
  end?: string;
  /** Only memories this person wrote or is mentioned in. */
  person_id?: UUID;
}

export interface SentimentStatus {
  enabled: boolean;
  /** Are transformers + torch installed on the server? */
  installed: boolean;
  model: string;
  done: number;
  remaining: number;
  /** Is an "Analyse now" run going on? */
  running: boolean;
}

// ---------- Ask ----------
export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}
export interface AskRequest {
  question: string;
  conversation?: ChatTurn[];
}

export type Confidence = "high" | "medium" | "low" | "none";

export interface AskAnalysis {
  intent: string;
  people: string[];
  time_start: ISODateString | null;
  time_end: ISODateString | null;
  temporal_order: "first" | "last" | null;
  modality: string[];
  rewritten_queries: string[];
}

/** The contract does not pin the shape of a step's `detail`, so accept any JSON value. */
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface TraceStep {
  name: string;
  latency_ms: number;
  detail?: JsonValue;
}

export interface AskTrace {
  steps: TraceStep[];
  provider: string | null;
  model: string | null;
  degraded: boolean;
  /** Set when the fine-tuning phase's derived model helped with this answer; null = standard models only. */
  finetune?: FinetuneInfo | null;
}

/** The two fine-tuning labels: the standard model training started from, and the model trained from it. */
export interface FinetuneInfo {
  base_model: string; // e.g. "gpt-4.1-nano-2025-04-14"
  derived_model: string; // e.g. "ft:gpt-4.1-nano-2025-04-14:personal:derived:AbC123"
}

export interface AskResponse {
  /** Cites evidence as [1], [2] … (1-based index into `evidence`). */
  answer: string;
  evidence: Evidence[];
  confidence: Confidence;
  analysis: AskAnalysis;
  trace: AskTrace;
}

// Payloads of the server-sent events on POST /ask/stream.
/** `event: step` */
export interface AskStepEvent {
  name: string;
  detail: JsonValue;
}
/** `event: token` */
export interface AskTokenEvent {
  text: string;
}
/** `event: error` */
export interface AskErrorEvent {
  message: string;
}

// ---------- Timeline ----------
export type Granularity = "year" | "month" | "day";

export interface TimelineBucket {
  /** "2024" | "2024-06" | "2024-06-14" */
  period: string;
  count: number;
  sources: Record<string, number>;
  top_people: string[];
}
export interface TimelineResponse {
  buckets: TimelineBucket[];
}
export interface TimelineParams {
  granularity: Granularity;
  /** Inclusive YYYY-MM-DD. */
  start?: string;
  /** Inclusive YYYY-MM-DD. */
  end?: string;
}
export interface DayResponse {
  date: string;
  memories: Evidence[];
}

// ---------- People ----------
export interface Person {
  id: UUID;
  display_name: string;
  aliases: string[];
  memory_count: number;
  first_seen: ISODateString | null;
  last_seen: ISODateString | null;
}

export interface PersonActivity {
  period: string;
  count: number;
}
export interface PersonConversation {
  id: UUID;
  title: string;
  memory_count: number;
}
export interface RelatedPerson {
  id: UUID;
  display_name: string;
  weight: number;
}

export interface PersonDetail extends Person {
  timeline: PersonActivity[];
  conversations: PersonConversation[];
  related_people: RelatedPerson[];
}

export interface AliasSuggestion {
  alias_id: UUID;
  alias: string;
  person_id: UUID;
  person_name: string;
  similarity: number;
}

export type AliasAnswer = "yes" | "no" | "unsure";
export interface AliasFeedbackRequest {
  alias_id: UUID;
  person_id: UUID;
  answer: AliasAnswer;
}
export interface OkResponse {
  ok: true;
}

// ---------- AI Lab ----------
export interface ProviderUsageRow {
  provider: string;
  model: string;
  task: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens?: number; // input tokens served from OpenAI's prompt cache
  errors: number;
  avg_latency_ms: number;
  day: string;
}
export interface LabUsage {
  providers: ProviderUsageRow[];
  limits: {
    max_daily_requests: number;
    max_monthly_requests: number;
    // Token budget: at most max_tokens_per_window tokens every token_window_hours hours (0 = no budget).
    max_tokens_per_window?: number;
    token_window_hours?: number;
    tokens_used_in_window?: number;
    token_window_resets_at?: string;
  };
}
export interface LabConfig {
  providers: { name: string; configured: boolean }[];
  routing: Record<string, string[]>;
  embedding_model: string;
  embedding_dim: number;
  reranker: string | null;
  top_k: number;
}

// ---------- Health ----------
export interface Health {
  status: "ok";
  db: boolean;
  redis: boolean;
}
