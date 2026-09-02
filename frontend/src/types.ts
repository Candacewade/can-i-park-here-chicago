export type ParkingStatus = "LEGAL" | "NOT_LEGAL" | "LEGAL_UNTIL" | "UNKNOWN";

export interface SideOption {
  side: string;
  location_id: string;
}
export interface BlockOption {
  from_cross_street: string;
  to_cross_street: string;
  sides: SideOption[];
}
export interface StreetOption {
  street_name: string;
  blocks: BlockOption[];
}
export interface NeighborhoodOption {
  name: string;
  streets: StreetOption[];
}
export interface LocationsResponse {
  generated: boolean;
  source: string;
  neighborhoods: NeighborhoodOption[];
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
  run_id: string;
  model: string;
  duration_ms: number | null;
  trace: ToolCallView[];
}

export interface ParkingSelection {
  neighborhood: string;
  street_name: string;
  from_cross_street: string;
  to_cross_street: string;
  side: string;
  location_id: string;
  start_date: string;
  start_time: string;
  end_date: string;
  end_time: string;
  permit_zone: string;
}
