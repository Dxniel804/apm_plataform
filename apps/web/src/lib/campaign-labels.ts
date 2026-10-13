import { formatWait } from "@/lib/auth-messages";
import type { ApiError, CampaignStatus } from "@/lib/api/types";
import type { StatusTone } from "@/lib/status";

/**
 * Textos em portugues para as campanhas. A API manda codigos (DRAFT, campaign_needs_a_product...); nenhum
 * texto do servidor e mostrado. Codigo desconhecido cai num texto generico, nunca num "deu certo".
 */
export function campaignStatusView(status: CampaignStatus): { label: string; tone: StatusTone } {
  switch (status) {
    case "DRAFT":
      return { label: "Rascunho", tone: "neutral" };
    case "ACTIVE":
      return { label: "À venda", tone: "success" };
    case "ENDED":
      return { label: "Encerrada", tone: "info" };
  }
}

/** Limites do banco (a tela avisa antes; a API confere de novo). Em centavos. */
export const MIN_PRICE_CENTS = 100;
export const MAX_PRICE_CENTS = 1_000_000;
export const MAX_ITEMS = 50;
/** O maior arquivo de imagem que a API aceita para a capa e os produtos. */
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export interface CampaignProblemText {
  general: string | null;
  /** Por nome de campo da API (title, price_cents, ends_on, file...). */
  fields: Record<string, string>;
}

const NETWORK = "Não foi possível falar com o servidor. Confira a conexão e tente de novo. Nada foi alterado.";
const GENERIC = "Algo deu errado do nosso lado. Tente de novo em instantes.";
const STALE = "Outra pessoa acabou de mexer nesta campanha. Atualize a lista e tente de novo.";

const FIELD_TEXT: Record<string, Record<string, string>> = {
  title: { required: "Escreva o título da campanha.", invalid: "O título precisa ter de 1 a 120 caracteres." },
  description: { invalid: "O texto pode ter até 2000 caracteres." },
  starts_on: { invalid: "Confira a data de início." },
  ends_on: {
    invalid: "Confira a data de fim.",
    before_start: "A data de fim não pode ser antes da data de início.",
    in_the_past: "A data de fim já passou: escolha uma data de hoje em diante.",
  },
  name: { required: "Escreva o nome do produto.", invalid: "O nome precisa ter de 1 a 120 caracteres." },
  price_cents: { required: "Informe o preço.", invalid: "O preço vai de R$ 1,00 a R$ 10.000,00." },
  max_per_order: { invalid: "O limite por pedido vai de 1 a 99." },
  file: {
    required: "Escolha uma imagem.",
    empty: "O arquivo está vazio.",
    image_malformed: "Esta imagem está corrompida ou não é PNG, JPEG ou WebP.",
    image_dimensions: "A imagem é grande demais em pixels. O limite é de 8000 pixels de lado.",
    image_type: "Tipo de arquivo não aceito. Envie uma imagem PNG, JPEG ou WebP.",
  },
};

/** Erro de uma acao sobre campanha (criar, editar, produto, imagem, pôr à venda, encerrar). */
export function describeCampaignError(error: ApiError): CampaignProblemText {
  const none: CampaignProblemText = { general: null, fields: {} };
  if (error.kind === "network" || error.kind === "timeout") return { ...none, general: NETWORK };
  if (error.status === 411 || error.status === 413) return { ...none, general: "A imagem é grande demais. O limite é de 5 MB." };
  if (error.kind !== "problem") return { ...none, general: GENERIC };

  switch (error.code) {
    case "unauthenticated":
    case "session_revoked":
      return { ...none, general: "Sua sessão terminou. Entre de novo." };
    case "permission_denied":
      return { ...none, general: "Você não tem permissão para mexer nas campanhas." };
    case "not_found":
      return { ...none, general: "Não encontramos esta campanha ou este produto. Atualize a lista." };
    case "invalid_state":
      return { ...none, general: "Esta campanha mudou de situação e essa ação não vale mais. Atualize a lista." };
    case "campaign_needs_a_product":
      return { ...none, general: "Adicione e deixe ligado pelo menos um produto antes de pôr a campanha à venda." };
    case "item_limit":
      return { ...none, general: `Uma campanha tem no máximo ${MAX_ITEMS} produtos.` };
    case "attachment_type_not_allowed":
      return { ...none, general: "Tipo de arquivo não aceito. Envie uma imagem PNG, JPEG ou WebP." };
    case "payload_too_large":
    case "length_required":
      return { ...none, general: "A imagem é grande demais. O limite é de 5 MB." };
    case "attachment_unavailable":
      return { ...none, general: "A imagem não está disponível agora. Avise a administração." };
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
      const out: CampaignProblemText = { general: null, fields: {} };
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

/** "5 de junho" / "5 a 30 de junho": o periodo em que a campanha esta a venda, por extenso e curto. */
export function describePeriod(startsOn: string | null, endsOn: string | null): string | null {
  const day = (iso: string) => {
    const [year, month, date] = iso.split("-").map(Number);
    return new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "short", timeZone: "UTC" }).format(Date.UTC(year!, month! - 1, date!));
  };
  if (startsOn && endsOn) return `${day(startsOn)} a ${day(endsOn)}`;
  if (endsOn) return `até ${day(endsOn)}`;
  if (startsOn) return `a partir de ${day(startsOn)}`;
  return null;
}
