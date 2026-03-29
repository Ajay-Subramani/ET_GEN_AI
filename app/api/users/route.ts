import type { UsersResponse } from "@/lib/ai-investor";

export const runtime = "nodejs";

export async function GET() {
  const body: UsersResponse = {
    default_user_id: "user_default",
    user_portfolio: {
      user_id: "user_default",
      risk_profile: "moderate",
      total_capital: 0,
      holdings: [],
    },
  };
  return Response.json(body, { status: 200 });
}
