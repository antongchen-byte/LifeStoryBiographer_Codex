import { boundedBody } from "../../../lib/request-body";
import { NextRequest, NextResponse } from "next/server";
export async function POST(request: NextRequest) {
  if (
    request.headers.get("origin") !==
    new URL(process.env.AUTH_URL ?? "http://localhost:3000").origin
  )
    return NextResponse.json(
      { detail: "Invalid request origin" },
      { status: 403 },
    );
  const body = await boundedBody(request, 4096);
  if (body === null)
    return NextResponse.json(
      { detail: "Request is too large" },
      { status: 413 },
    );
  try {
    const response = await fetch(
      `${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/auth/register`,
      {
        method: "POST",
        body,
        headers: { "Content-Type": "application/json" },
      },
    );
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "The application service is unavailable." },
      { status: 503 },
    );
  }
}
