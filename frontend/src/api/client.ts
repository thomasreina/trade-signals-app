import axios from "axios";
import type { AnalysisResponse } from "./types";

const BASE = "/api";

export async function fetchAnalysis(
  symbol: string,
  timeframe: string,
  limit = 200,
): Promise<AnalysisResponse> {
  const { data } = await axios.get<AnalysisResponse>(
    `${BASE}/analysis/${symbol}`,
    { params: { timeframe, limit } },
  );
  return data;
}
