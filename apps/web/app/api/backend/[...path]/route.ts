import { boundedBody } from "../../../../lib/request-body";
import { getToken } from "next-auth/jwt";
import { NextRequest, NextResponse } from "next/server";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const token = await getToken({
    req: request,
    secret: process.env.AUTH_SECRET,
    secureCookie: (process.env.AUTH_URL ?? "").startsWith("https://"),
  });
  if (!token?.backendToken)
    return NextResponse.json({ detail: "Please sign in" }, { status: 401 });
  const mutates = !["GET", "HEAD"].includes(request.method);
  if (
    mutates &&
    request.headers.get("origin") !==
      new URL(process.env.AUTH_URL ?? "http://localhost:3000").origin
  )
    return NextResponse.json(
      { detail: "Invalid request origin" },
      { status: 403 },
    );
  const { path } = await context.params;
  if (
    path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part)) ||
    ![
      "projects",
      "profiles",
      "jobs",
      "interviews",
      "cinema",
      "photos",
    ].includes(path[0])
  )
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  // A 10,000-part manifest can exceed the normal JSON request limit.
  const completesUpload =
    request.method === "POST" &&
    path.length === 5 &&
    path[0] === "projects" &&
    path[2] === "media" &&
    path[4] === "complete";
  const body = mutates
    ? await boundedBody(
        request,
        path[0] === "interviews" &&
          path.length === 4 &&
          path[1] === "sessions" &&
          ["turns", "finish"].includes(path[3])
          ? 18 * 1024 * 1024
          : path[0] === "interviews" && path[1] === "screenplays"
            ? 2 * 1024 * 1024
            : completesUpload
              ? 2 * 1024 * 1024
              : 262144,
      )
    : undefined;
  if (body === null)
    return NextResponse.json(
      { detail: "Request is too large" },
      { status: 413 },
    );
  try {
    const response = await fetch(
      `${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/${path.join("/")}${request.nextUrl.search}`,
      {
        method: request.method,
        body,
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token.backendToken}`,
        },
      },
    );
    return new NextResponse(
      response.status === 204 ? null : await response.text(),
      {
        status: response.status,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
      },
    );
  } catch {
    return NextResponse.json(
      { detail: "The application service is unavailable. Please try again." },
      { status: 503 },
    );
  }
}
export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
};
