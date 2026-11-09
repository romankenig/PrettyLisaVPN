import type { ApiClient } from "../api/client";
import type { HttpTransport } from "../native/http";
import type { AuthenticationSession } from "./session";

/** Resolve a current bearer for every authenticated API, including idle UI reads. */
export function createSessionTransport(
  baseUrl: string,
  transport: HttpTransport,
  session: AuthenticationSession,
  api: Pick<ApiClient, "refresh" | "me">,
): HttpTransport {
  const base = new URL(baseUrl);
  return async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    const headers = new Headers(
      init?.headers ?? (input instanceof Request ? input.headers : undefined),
    );
    const authorization = headers.get("Authorization");
    if (!authorization) return transport(input, init);
    if (
      url.origin !== base.origin ||
      !url.pathname.startsWith(base.pathname.replace(/\/$/, "") + "/")
    )
      throw new Error("AUTH_DESTINATION_INVALID");
    const owner = session.current();
    if (!owner || authorization !== `Bearer ${owner.accessToken}`)
      throw new Error("AUTH_CHANGED");
    const assertCurrent = () => {
      init?.signal?.throwIfAborted();
      if (
        session.current()?.sessionId !== owner.sessionId ||
        session.current()?.userId !== owner.userId
      )
        throw new Error("AUTH_CHANGED");
    };
    const send = async (rejectedToken?: string) => {
      const token = await session.bearer(api, rejectedToken);
      assertCurrent();
      headers.set("Authorization", `Bearer ${token}`);
      const response = await transport(
        input instanceof Request ? input.clone() : input,
        { ...init, headers },
      );
      assertCurrent();
      return { response, token };
    };
    const first = await send();
    if (first.response.status !== 401) return first.response;
    const code = await first.response
      .clone()
      .json()
      .then((body: { error?: { code?: string } }) => body.error?.code)
      .catch(() => undefined);
    if (code !== "invalid_access_token") return first.response;
    assertCurrent();
    return (await send(first.token)).response;
  };
}
