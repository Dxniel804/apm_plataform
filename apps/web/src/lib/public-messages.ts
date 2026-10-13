import { formatWait } from "@/lib/auth-messages";
import type { ApiError } from "@/lib/api/types";
import { FIELD_FROM_API, MISSING_MESSAGES, type IdentificationErrors } from "@/lib/validation";

/**
 * Textos em portugues para os erros do portal publico, escolhidos pelo `code` e pelo
 * `errors[].field`/`code` do problem+json. O title/detail do servidor NUNCA aparece.
 */
const NETWORK = "Não foi possível falar com o servidor. Confira a conexão e tente de novo. Nada foi cobrado.";
const GENERIC = "Não foi possível gerar o Pix agora. Tente de novo em instantes. Nada foi cobrado.";
const UNAVAILABLE = "O Pix ainda não está disponível para esta escola. Fale com a gestão da APM.";

export interface ContributionProblems {
  general: string | null;
  amount: string | null;
  fields: IdentificationErrors;
}

function rateLimited(error: ApiError): string {
  return `Muitas tentativas seguidas. Aguarde ${formatWait(error.retryAfterSeconds)} e tente de novo.`;
}

/** Erro do POST de criacao da contribuicao: geral, do valor e de cada campo. */
export function describeContributionError(error: ApiError): ContributionProblems {
  const none: ContributionProblems = { general: null, amount: null, fields: {} };
  if (error.kind === "network" || error.kind === "timeout") return { ...none, general: NETWORK };
  if (error.status === 501) return { ...none, general: UNAVAILABLE };
  if (error.kind !== "problem") return { ...none, general: GENERIC };

  switch (error.code) {
    case "rate_limited":
      return { ...none, general: rateLimited(error) };
    case "not_found":
      return { ...none, general: "Não encontramos esta escola. Confira o endereço que a escola enviou." };
    case "idempotency_key_reused":
      return { ...none, general: "Algo mudou entre uma tentativa e outra. Confira os dados e tente de novo." };
    case "validation_error": {
      const out: ContributionProblems = { general: null, amount: null, fields: {} };
      for (const item of error.fields ?? []) {
        if (item.field === "amount_cents") {
          out.amount =
            item.code === "not_suggested"
              ? "Esta escola aceita só os valores sugeridos."
              : item.code === "out_of_range"
                ? "O valor não está dentro do que a escola aceita."
                : "Confira o valor da contribuição.";
        } else if (item.field in FIELD_FROM_API) {
          const field = FIELD_FROM_API[item.field]!;
          out.fields[field] = item.code === "required" ? MISSING_MESSAGES[field] : "Confira este campo.";
        } else {
          out.general = "Não foi possível enviar o pedido. Recarregue a página e tente de novo.";
        }
      }
      if (!out.general && !out.amount && Object.keys(out.fields).length === 0) {
        out.general = "Algum dado não foi aceito pela escola. Volte e confira o valor e os campos.";
      }
      return out;
    }
    default:
      return { ...none, general: GENERIC };
  }
}

/** Erro de "gerar novo QR" (POST .../charges). */
export function describeRenewError(error: ApiError): string {
  if (error.kind === "network" || error.kind === "timeout") return NETWORK;
  if (error.status === 501) return UNAVAILABLE;
  if (error.kind === "problem") {
    if (error.code === "rate_limited") return rateLimited(error);
    if (error.code === "contribution_closed") return "Esta contribuição não está mais aguardando pagamento. Comece uma nova.";
  }
  return "Não foi possível gerar um novo QR agora. Tente de novo em instantes.";
}

/** Erro do registro de contribuicao em dinheiro pela gestao (POST /schools/{id}/contributions). */
export function describeCashError(error: ApiError): ContributionProblems {
  const none: ContributionProblems = { general: null, amount: null, fields: {} };
  if (error.kind === "network" || error.kind === "timeout") return { ...none, general: "Não foi possível falar com o servidor. Confira a conexão e tente de novo. Nada foi registrado." };
  if (error.kind === "problem") {
    switch (error.code) {
      case "validation_error": {
        const out: ContributionProblems = { general: null, amount: null, fields: {} };
        for (const item of error.fields ?? []) {
          if (item.field === "amount_cents") out.amount = "Confira o valor da contribuição.";
          else if (item.field in FIELD_FROM_API) out.fields[FIELD_FROM_API[item.field]!] = "Confira este campo.";
          else out.general = "Confira os dados informados e tente de novo.";
        }
        if (!out.amount && !out.general && Object.keys(out.fields).length === 0) out.general = "Confira os dados informados e tente de novo.";
        return out;
      }
      case "permission_denied":
        return { ...none, general: "Você não tem permissão para registrar contribuições." };
      case "unauthenticated":
      case "session_revoked":
        return { ...none, general: "Sua sessão terminou. Entre de novo." };
      case "rate_limited":
        return { ...none, general: rateLimited(error) };
      case "csrf_failed":
      case "origin_not_allowed":
        return { ...none, general: "Não foi possível confirmar que o pedido saiu desta página. Recarregue a página e tente de novo." };
      case "idempotency_key_reused":
        return { ...none, general: "Algo mudou entre uma tentativa e outra. Confira os dados e tente de novo." };
      default:
        break;
    }
  }
  return { ...none, general: "Não foi possível registrar agora. Tente de novo em instantes. Nada foi registrado." };
}

/** Erro do POST do pedido de uma campanha: geral e, por linha do carrinho, o que nao serve mais. */
export interface OrderProblems {
  general: string | null;
  /** Por indice da linha do carrinho (`lines[2].quantity` -> 2): o que o servidor recusou nela. */
  lines: Record<number, string>;
  fields: IdentificationErrors;
}

const LINE_PATTERN = /^lines\[(\d+)\]\.(item_id|quantity)$/;

export function describeOrderError(error: ApiError): OrderProblems {
  const none: OrderProblems = { general: null, lines: {}, fields: {} };
  if (error.kind === "network" || error.kind === "timeout") return { ...none, general: NETWORK };
  if (error.status === 501) return { ...none, general: UNAVAILABLE };
  if (error.kind !== "problem") return { ...none, general: GENERIC };

  switch (error.code) {
    case "rate_limited":
      return { ...none, general: rateLimited(error) };
    case "not_found":
      return { ...none, general: "Esta campanha não está mais à venda. Volte à página da escola para ver o que está disponível." };
    case "campaign_changed":
      return { ...none, general: "A campanha mudou enquanto você montava o pedido. Confira os produtos e os preços e tente de novo." };
    case "idempotency_key_reused":
      return { ...none, general: "Algo mudou entre uma tentativa e outra. Confira o carrinho e tente de novo." };
    case "payment_unavailable":
      return { ...none, general: "Esta escola ainda não pode receber pelo Pix. Fale com a gestão da APM." };
    case "validation_error": {
      const out: OrderProblems = { general: null, lines: {}, fields: {} };
      for (const item of error.fields ?? []) {
        const line = LINE_PATTERN.exec(item.field);
        if (line) {
          out.lines[Number(line[1])] =
            item.code === "over_limit"
              ? "Passa do limite por pedido deste produto."
              : item.code === "duplicate"
                ? "Este produto aparece duas vezes."
                : "Este produto não está mais à venda.";
        } else if (item.field === "lines") {
          out.general = "O total do pedido passa do limite de R$ 50.000,00. Tire alguns itens.";
        } else if (item.field in FIELD_FROM_API) {
          const field = FIELD_FROM_API[item.field]!;
          out.fields[field] = item.code === "required" ? MISSING_MESSAGES[field] : "Confira este campo.";
        } else {
          out.general = "Não foi possível enviar o pedido. Recarregue a página e tente de novo.";
        }
      }
      if (!out.general && Object.keys(out.lines).length === 0 && Object.keys(out.fields).length === 0) {
        out.general = "Algum dado do pedido não foi aceito. Volte e confira o carrinho.";
      }
      return out;
    }
    default:
      return { ...none, general: GENERIC };
  }
}
