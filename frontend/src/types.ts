export type ParkingStatus = "LEGAL" | "NOT_LEGAL" | "LEGAL_UNTIL" | "UNKNOWN";

export interface ExampleAddress {
  label: string;
  number: number;
  street: string;
  zip_code: string;
}

export interface SideCandidate {
  side: string;
  location_id: string;
  summary: string;
  /** From the City's own Permit Parking Zones dataset for this exact block +
   * side -- not a neighborhood-level guess. Null + not a buffer zone means no
   * residential permit is required here. */
  required_permit_zone: string | null;
  permit_zone_is_buffer: boolean;
}

export interface ResolveResponse {
  in_chicago: boolean;
  matched_address: string | null;
  street_name: string | null;
  neighborhood: string | null;
  from_cross_street: string | null;
  to_cross_street: string | null;
  street_sweeping_ward: string | null;
  street_sweeping_section: string | null;
  latitude: number | null;
  longitude: number | null;
  suggested_side: string | null;
  side_confidence: string;
  side_options: SideCandidate[];
  notes: string[];
}

export interface DecisionReason {
  category: string;
  verdict: string;
  detail: string;
  source_dataset_id?: string | null;
}

export interface ToolCallView {
  order: number;
  name: string;
  status: string;
  latency_ms: number | null;
  arguments: Record<string, unknown>;
  result_preview: string;
}

export interface AnalyzeResponse {
  status: ParkingStatus;
  move_by: string | null;
  start_time_display: string | null;
  end_time_display: string | null;
  move_by_display: string | null;
  urgent_alert: boolean;
  urgent_reason: string | null;
  summary: string;
  reasons: DecisionReason[];
  unknown_reasons: string[];
  completeness_complete: boolean;
  core_status: ParkingStatus | null;
  agent_available: boolean;
  run_id: string;
  model: string;
  duration_ms: number | null;
  trace: ToolCallView[];
}

export interface CreateWatchResponse {
  watch_id: string;
  manage_token: string;
  email_registered: boolean;
  note: string;
}

export interface ReplaceWatchResponse {
  old_watch_id: string;
  watch_id: string;
  manage_token: string;
  email_registered: boolean;
}

export interface ExtendWatchResponse {
  watch_id: string;
  manage_token: string;
  end_time: string;
  end_time_local: string;
  through_display: string;
  status: ParkingStatus;
  start_time_display: string | null;
  end_time_display: string | null;
  move_by_display: string | null;
  urgent_alert: boolean;
  summary: string;
}

/** Lightweight, persisted in localStorage. No account, no server session. */
export interface MonitorState {
  watchId: string;
  token: string;
  email?: string;
  locationSummary?: string;
  throughDisplay?: string;
  /** "YYYY-MM-DDTHH:MM" America/Chicago wall time — prefills the extend form. */
  endLocal?: string;
}

/** A self-reported correction to a watch's status (e.g. a posted sign the
 * data doesn't reflect). NOT verified -- see docs/monitoring.md. Present on
 * WatchView/WatchListItem only while still active (not yet expired). */
export interface WatchOverrideView {
  status: ParkingStatus;
  move_by: string | null;
  move_by_display: string | null;
  note: string;
  reported_at: string;
  expires_at: string;
  expires_at_local: string;
}

export interface SetWatchOverrideResponse {
  watch_id: string;
  override: WatchOverrideView;
  status: ParkingStatus;
  move_by_display: string | null;
  summary: string;
}

export interface WatchView {
  watch_id: string;
  location_id: string;
  start_time: string;
  end_time: string;
  permit_zone: string | null;
  status: string;
  created_at: string;
  last_decision: string | null;
  last_checked_at: string | null;
  notified_count: number;
  location_summary: string | null;
  through_display: string | null;
  end_time_local: string | null;
  override: WatchOverrideView | null;
}

/** One row in the "find my watches" list -- unlike WatchView, carries its own
 * manage_token since the caller only proved control of the email, not this
 * specific watch, before seeing this list. */
export interface WatchListItem extends WatchView {
  manage_token: string;
}

export interface AddressInput {
  number: string;
  street: string;
  zip: string;
}

export interface WhenInput {
  start_date: string;
  start_time: string;
  end_date: string;
  end_time: string;
  permit_zone: string;
}
