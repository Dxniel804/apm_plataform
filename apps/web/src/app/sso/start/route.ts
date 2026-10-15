import { proxySso } from "@/lib/forklin";

export const dynamic = "force-dynamic";

export function GET(request: Request): Promise<Response> {
  return proxySso(request, "start");
}
