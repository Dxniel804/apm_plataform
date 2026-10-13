import { formatWait } from "@/lib/auth-messages";
import type { ApiError, RequestCategory, RequestStatus } from "@/lib/api/types";
import type { StatusTone } from "@/lib/status";

/**
 * Textos em portugues para as solicitacoes. A API manda codigos (OPEN, SUPPLIES, author_only...); nenhum
 * texto do servidor e mostrado. Codigo desconhecido cai num texto generico, nunca num "deu certo".
 */
export const CATEGORY_LABELS: Record<RequestCategory, string> = {
  SUPPLIES: "Compra de material",
  MAINTENANCE: "Manutenção",
  EVENT: "Evento",
  FINANCE: "Financeiro",
  OTHER: "Outros",
};

export const CATEGORY_ORDER: readonly RequestCategory[] = ["SUPPLIES", "MAINTENANCE", "EVENT", "FINANCE", "OTHER"];

export function requestStatusView(status: RequestStatus): { label: string; tone: StatusTone } {
  switch (status) {
    case "OPEN":
      return { label: "Aberta", tone: "info" };
    case "IN_PROGRESS":
      return { label: "Em andamento", tone: "warning" };
    case "RESOLVED":
      return { label: "Resolvida", tone: "success" };
    case "CANCELLED":
      return { label: "Cancelada", tone: "neutral" };
  }
}

export const MAX_PHOTOS = 6;
export const MAX_PHOTO_BYTES = 10 * 1024 * 1024;

export interface RequestProblemText {
  general: string | null;
  /** Por nome de campo da API (title, category, note...). */
  fields: Record<string, string>;
}

const NETWORK = "Não foi possível falar com o servidor. Confira a conexão e tente de novo. Nada foi alterado.";
const GENERIC = "Algo deu errado do nosso lado. Tente de novo em instantes.";
const STALE = "Outra pessoa acabou de mexer nesta solicitação. Atualize a lista e tente de novo.";

const FIELD_TEXT: Record<string, Record<string, string>> = {
  category: { invalid: "Escolha uma categoria da lista.", required: "Escolha uma categoria." },
  title: { required: "Escreva o título do pedido.", invalid: "O título precisa ter de 1 a 120 caracteres." },
  description: { invalid: "A descrição pode ter até 2000 caracteres." },
  note: { invalid: "A resposta precisa ter de 1 a 1000 caracteres." },
};

/** Erro de uma acao sobre solicitacao (abrir, anexar foto, iniciar, resolver, cancelar). */
export function describeRequestError(error: ApiError): RequestProblemText {
  const none: RequestProblemText = { general: null, fields: {} };
  if (error.kind === "network" || error.kind === "timeout") return { ...none, general: NETWORK };
  if (error.status === 411 || error.status === 413) return { ...none, general: "A foto é grande demais. O limite é de 10 MB." };
  if (error.kind !== "problem") return { ...none, general: GENERIC };

  switch (error.code) {
    case "unauthenticated":
    case "session_revoked":
      return { ...none, general: "Sua sessão terminou. Entre de novo." };
    case "permission_denied":
      return { ...none, general: "Você não tem permissão para fazer isso." };
    case "author_only":
      return { ...none, general: "Só quem abriu a solicitação pode fazer isso." };
    case "not_found":
      return { ...none, general: "Não encontramos esta solicitação. Atualize a lista." };
    case "invalid_state":
      return { ...none, general: "Esta solicitação mudou de situação e essa ação não vale mais. Atualize a lista." };
    case "attachments_closed":
      return { ...none, general: "A solicitação já foi respondida: só dá para anexar fotos enquanto ela está aberta." };
    case "attachment_limit":
      return { ...none, general: `Esta solicitação já tem o máximo de ${MAX_PHOTOS} fotos.` };
    case "attachment_duplicate":
      return { ...none, general: "Esta foto já foi anexada." };
    case "attachment_type_not_allowed":
      return { ...none, general: "Tipo de arquivo não aceito. Envie uma foto PNG, JPEG ou WebP." };
    case "payload_too_large":
    case "length_required":
      return { ...none, general: "A foto é grande demais. O limite é de 10 MB." };
    case "attachment_unavailable":
      return { ...none, general: "A foto não está disponível agora. Avise a administração." };
    case "conflict":
    case "state_conflict":
    case "retry":
      return { ...none, general: STALE };
    case "rate_limited":
      return { ...none, general: `Muitas tentativas seguidas. Aguarde ${formatWait(error.retryAfterSeconds)} e tente de novo.` };
    case "csrf_failed":
    case "origin_not_allowed":
      return { ...none, general: "Não foi possível confirmar que o pedido saiu desta página. Recarregue a página e tente de novo." };
    case "validation_error":
    case "rule_violation":
    case "reference_invalid":
    case "value_out_of_range": {
      const out: RequestProblemText = { general: null, fields: {} };
      for (const item of error.fields ?? []) {
        out.fields[item.field] = FIELD_TEXT[item.field]?.[item.code] ?? "Confira este campo.";
      }
      if (Object.keys(out.fields).length === 0) out.general = "Confira os dados informados e tente de novo.";
      return out;
    }
    default:
      return { ...none, general: error.status === 409 ? STALE : GENERIC };
  }
}
