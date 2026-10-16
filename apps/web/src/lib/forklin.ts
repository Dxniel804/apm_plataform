import { serverApiOrigin } from "@/lib/api/server";

/**
 * "Entrar com Forklin" (docs/adr-forklin-sso.md). So o SERVIDOR do Next le a flag: ligada, a tela de
 * entrada mostra o botao e /sso/* repassa a API. Desligada (padrao), nada muda e /sso/* responde 404.
 */
export function forklinEnabled(env: string | undefined = process.env.FORKLIN_CORE_ENABLED): boolean {
  return env?.trim().toLowerCase() === "true";
}

/**
 * Com a Central ligada as pessoas so existem la: o APM nao cadastra equipe. Tira "invitations:create"
 * das permissoes para o painel nao mostrar nem abrir "Equipe" (a API tambem responde 404; isto so
 * esconde). Desligada, devolve a sessao como veio.
 */
export function withoutStaffRegistration<T extends { activeMembership: { permissions: string[] } | null }>(
  session: T,
  on: boolean = forklinEnabled(),
): T {
  if (!on || !session.activeMembership) return session;
  const permissions = session.activeMembership.permissions.filter((p) => p !== "invitations:create");
  return { ...session, activeMembership: { ...session.activeMembership, permissions } };
}

/** As palavras que a API manda em /login?erro=. Qualquer outra vira a frase generica. */
type SsoProblem = { title: string; message: string };

const GENERIC: SsoProblem = {
  title: "Entrada indisponível",
  message: "Não foi possível falar com a Forklin agora. Tente de novo em instantes.",
};

const SSO_ERRORS: Record<string, SsoProblem> = {
  org: {
    title: "Organização sem acesso",
    message: "Este sistema ainda não está disponível para a sua organização. Fale com a secretaria da escola.",
  },
  acesso: {
    title: "Sem acesso",
    message: "Você não tem acesso ao APM Digital. Peça à secretaria da escola para liberar a sua conta.",
  },
  cargo: {
    title: "Cargo não reconhecido",
    message: "O seu cargo na Forklin não existe no APM Digital. Fale com a secretaria da escola.",
  },
  conflito: {
    title: "Conta em conflito",
    message: "Já existe uma conta com este e-mail ligada a outra pessoa. Fale com o suporte.",
  },
  expirado: {
    title: "Entrada expirada",
    message: "O link de entrada venceu ou já foi usado. Tente entrar de novo.",
  },
  indisponivel: GENERIC,
};

export function describeSsoError(word: string | string[] | undefined): SsoProblem | null {
  const key = Array.isArray(word) ? word[0] : word;
  if (!key) return null;
  return (Object.hasOwn(SSO_ERRORS, key) ? SSO_ERRORS[key] : undefined) ?? GENERIC;
}

/**
 * Repassa /sso/start e /sso/callback a API, sem seguir o redirecionamento: o navegador recebe o
 * mesmo 302 (Location relativo) e os cookies que a API grava (sessao, CSRF, state). Nada de corpo.
 */
export async function proxySso(
  request: Request,
  action: "start" | "callback",
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  if (!forklinEnabled()) return new Response(null, { status: 404, headers: { "Cache-Control": "no-store" } });
  const search = action === "callback" ? new URL(request.url).search : "";
  const headers: Record<string, string> = { Accept: "text/html" };
  const cookie = request.headers.get("cookie");
  if (cookie) headers.Cookie = cookie;
  const agent = request.headers.get("user-agent");
  if (agent) headers["User-Agent"] = agent;
  let upstream: Response;
  try {
    upstream = await fetchImpl(`${serverApiOrigin()}/api/v1/forklin/sso/${action}${search}`, {
      method: "GET",
      headers,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    return new Response(null, { status: 302, headers: { Location: "/login?erro=indisponivel", "Cache-Control": "no-store" } });
  }
  const out = new Headers({ "Cache-Control": "no-store" });
  const location = upstream.headers.get("location");
  if (location) out.set("Location", location);
  for (const cookieLine of upstream.headers.getSetCookie()) out.append("Set-Cookie", cookieLine);
  return new Response(null, { status: upstream.status, headers: out });
}
