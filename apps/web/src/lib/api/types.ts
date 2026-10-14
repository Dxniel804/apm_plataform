/**
 * Tipos do contrato entre o frontend e a API.
 *
 * REAIS hoje (veja /api/openapi.json): GET /api/health, GET /api/health/ready e a autenticacao
 * (/api/v1/auth/* e /api/v1/invitations/accept, docs/auth.md). Os tipos de auth ficam em camelCase:
 * a conversao do snake_case da API acontece em src/lib/api/auth.ts, na fronteira.
 * TODO o resto e PROPOSTA (docs/web-contract-proposals.md), hoje simulada em src/mocks.
 * Dinheiro: sempre inteiro em centavos.
 */
import type { Cents } from "../money";
import type { IdentificationConfig, IdentificationValues } from "../validation";
import type { ContributionStatus, MovementKind, PixChargeStatus } from "../status";

// ---------------------------------------------------------------- resultado e erros

export type ApiErrorKind = "network" | "timeout" | "http" | "invalid-response" | "not-found" | "problem";

/** Erro de campo de um 422 (`errors[]` do problem+json): campo e codigo FIXO, nunca texto do servidor. */
export interface FieldError {
  field: string;
  code: string;
}

export interface ApiError {
  kind: ApiErrorKind;
  /** Status HTTP quando houve resposta. */
  status?: number;
  /**
   * `code` estavel de um application/problem+json (kind "problem"). E a UNICA parte do erro do
   * servidor que a interface usa: o texto em portugues vem do `code`, nunca de title/detail.
   */
  code?: string;
  /** Retry-After (segundos) de um 429, ja limitado a um intervalo razoavel. */
  retryAfterSeconds?: number;
  fields?: FieldError[];
  /** Mes (YYYY-MM) que a API nomeia em `closing_out_of_sequence`: o proximo a fechar. Nada alem do mes. */
  detailPeriod?: string;
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError };

// ---------------------------------------------------------------- REAL: health

/** GET /api/health/ready: 200 {"status":"ready"} ou 503 {"status":"unavailable"}. */
export type ReadinessStatus = "ready" | "unavailable";

export type ReadinessResult =
  | { state: "ready" }
  | { state: "unavailable"; reason: "not-ready" | "unreachable" };

// ---------------------------------------------------------------- REAL: autenticacao (docs/auth.md)

export const ROLES = ["school_admin", "treasurer", "staff", "viewer"] as const;
export type Role = (typeof ROLES)[number];

export interface AuthUser {
  id: string;
  email: string;
  fullName: string;
}

export interface OrganizationRef {
  id: string;
  name: string;
  slug: string;
}

export interface SchoolRef {
  id: string;
  slug: string;
  name: string;
}

/** Vinculo (membership): UMA escola, com um papel. Cada escola e um cliente: nao existe vinculo de rede (ADR-020). */
export interface Membership {
  membershipId: string;
  organization: OrganizationRef;
  school: SchoolRef;
  role: Role;
}

export interface ActiveMembership extends Membership {
  /** So para esconder o que a pessoa nao pode fazer. O servidor confere de novo a cada pedido. */
  permissions: string[];
}

/** Quem esta logado e onde atua. O token CSRF NAO entra aqui: o cliente le do cookie legivel. */
export interface Session {
  user: AuthUser;
  /** null enquanto a pessoa com varios vinculos ainda nao escolheu onde atuar. */
  activeMembership: ActiveMembership | null;
  memberships: Membership[];
  expiresAt: string;
  idleTimeoutSeconds: number;
}

export interface AcceptedInvitation {
  userId: string;
  membership: Membership;
}

export interface AcceptInvitationInput {
  token: string;
  /** Pessoa nova: nome e senha. Conta existente: so o token, com a pessoa logada. */
  fullName?: string;
  password?: string;
}

// ---------------------------------------------------------------- REAL: portal publico (docs/public-flow.md)

/** Configuracao publica da escola, resolvida pelo slug da URL (ADR-010). Sem id interno. */
export interface PublicSchool {
  slug: string;
  name: string;
  /** Nome curto da APM, ex.: "APM da Escola Exemplo". */
  apmName: string;
  /** Cor da escola (hex). O frontend deriva dai o tema com contraste AA. */
  accentColor: string;
  /** Valores sugeridos (centavos), na ordem da API. */
  suggestedAmountsCents: Cents[];
  /** false = so os valores sugeridos sao aceitos. */
  allowCustomAmount: boolean;
  minAmountCents: Cents;
  maxAmountCents: Cents;
  identification: IdentificationConfig;
}

export type ChargeStatus = PixChargeStatus;
export type { ContributionStatus };

export interface PixCharge {
  status: ChargeStatus;
  amountCents: Cents;
  /** Texto do "copia e cola" e do QR. No sandbox: `PIX-SANDBOX:<txid>:<valor>`. */
  emvPayload: string | null;
  expiresAt: string;
}

/** Estado da contribuicao e da cobranca mais recente (GET .../charge, POST .../charges). */
export interface ContributionState {
  status: ContributionStatus;
  amountCents: Cents;
  charge: PixCharge | null;
}

/** Resposta do POST de criacao: o token opaco (segredo da familia) so existe aqui e na URL do comprovante. */
export interface CreatedContribution extends ContributionState {
  token: string;
}

export interface CreateContributionInput {
  amountCents: Cents;
  identification: IdentificationValues;
}

/** Uma linha do que um pedido de campanha comprou, como foi comprado (nome e preco do dia). */
export interface ReceiptItem {
  name: string;
  unitPriceCents: Cents;
  quantity: number;
}

export interface Receipt {
  /** O comprovante so existe pago (a API responde 409 antes disso). */
  status: "PAID";
  referenceCode: string;
  amountCents: Cents;
  paidAt: string;
  schoolName: string;
  /** Forma de pagamento como a API manda (PIX, CASH, TRANSFER, OTHER). */
  method: string;
  /** So no pedido de uma campanha: o titulo e o que ele comprou (a soma e `amountCents`). */
  campaignTitle: string | null;
  items: ReceiptItem[];
}

// ---------------------------------------------------------------- REAL: extrato do painel (docs/statement.md)

/** Colunas de statement_summary: a API nao soma nada e o site tambem nao. Dinheiro em centavos. */
export interface StatementSummary {
  /** YYYY-MM no fuso da escola. */
  period: string;
  periodStart: string;
  periodEnd: string;
  timezone: string;
  openingBalanceCents: Cents;
  contributionsInCents: Cents;
  otherInCents: Cents;
  refundsInCents: Cents;
  totalInCents: Cents;
  /** Pagas pela APM, tarifas incluidas. */
  expensesOutCents: Cents;
  reimbursementsOutCents: Cents;
  totalOutCents: Cents;
  /** Saldo PRINCIPAL: em caixa. */
  closingBalanceCents: Cents;
  pendingReimbursementsCents: Cents;
  /** Saldo SECUNDARIO: o de caixa menos os reembolsos ainda a pagar. */
  balanceAfterPendingCents: Cents;
  entriesCount: number;
}

export interface StatementEntry {
  transactionId: string;
  referenceCode: number;
  kind: MovementKind;
  displayType: "INCOME" | "EXPENSE" | "REFUND";
  /** Quem manda se e entrada ou saida e a API, nao a tela. */
  direction: "IN" | "OUT";
  occurredAt: string;
  localDate: string;
  amountCents: Cents;
  signedAmountCents: Cents;
  lateAdjustment: boolean;
  /** Como a API manda (PAID...); a tela traduz. */
  status: string;
  /** Rotulo de status da API (PAID, REIMBURSED...), tambem em codigo: a tela traduz. */
  statusLabel: string;
  originLabel: string | null;
  beneficiaryLabel: string | null;
  categoryKey: string;
  description: string | null;
  runningBalanceCents: Cents;
}

/** Linha de statement_pending: fora do saldo (a pagar, em analise, a receber...). */
export interface PendingEntry {
  transactionId: string;
  referenceCode: number;
  kind: MovementKind;
  direction: "IN" | "OUT";
  status: string;
  amountCents: Cents;
  section: string;
  occurredAt: string;
}

export interface Page<T> {
  items: T[];
  nextCursor: string | null;
}

export type CashMethod = "CASH" | "TRANSFER" | "OTHER";
export type CashCategory = "parent_contribution" | "donation" | "other_income" | "apm_revenue";

export interface CashContributionInput {
  amountCents: Cents;
  method: CashMethod;
  categoryKey: CashCategory;
  identification: IdentificationValues;
}

export interface CashContributionResult {
  id: string;
  referenceCode: string;
  status: string;
  amountCents: Cents;
  method: string;
}


// ---------------------------------------------------------------- REAL: despesas (docs/expenses.md)

export type ExpenseStatus = "DRAFT" | "SUBMITTED" | "CORRECTION_REQUESTED" | "APPROVED" | "REJECTED" | "PAID" | "CANCELLED";
export type PaidBy = "APM" | "COLLABORATOR";
export type PaymentMethod = "PIX" | "CARD" | "CASH" | "OTHER";
export type AttachmentKind = "INVOICE" | "PAYMENT_PROOF" | "OTHER";

export interface ExpenseCategory {
  id: string;
  key: string;
  name: string;
}

export interface ExpenseSummary {
  id: string;
  referenceCode: number;
  status: ExpenseStatus;
  amountCents: Cents;
  /** So depois da aprovacao (pode ser menor que o pedido quando um colaborador pagou). */
  approvedAmountCents: Cents | null;
  category: ExpenseCategory;
  occurredAt: string;
  description: string;
  vendor: string | null;
  paidBy: PaidBy;
  /** A API devolve so o id de quem enviou (nao o nome): o site compara com o usuario da sessao. */
  submittedByUserId: string;
  attachmentsCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface Attachment {
  id: string;
  kind: AttachmentKind;
  fileName: string;
  contentType: string;
  sizeBytes: number;
  uploadedByUserId: string;
  createdAt: string;
}

export interface Reimbursement {
  id: string;
  status: "PENDING" | "PAID" | "CANCELLED";
  amountCents: Cents;
  beneficiaryUserId: string;
  paidByUserId: string | null;
  paymentReference: string | null;
  settledAt: string | null;
  createdAt: string;
}

export interface ExpenseDetail extends ExpenseSummary {
  purchaseReason: string | null;
  paymentMethod: PaymentMethod | null;
  approvedByUserId: string | null;
  approvedAt: string | null;
  decisionReason: string | null;
  /** O motivo que a gestao escreveu ao pedir correcao. */
  correctionReason: string | null;
  settledAt: string | null;
  attachments: Attachment[];
  reimbursement: Reimbursement | null;
}

export interface ExpenseInput {
  amountCents: Cents;
  /** Dia (YYYY-MM-DD, meio-dia no fuso da escola) ou instante ISO com fuso. */
  occurredAt: string;
  categoryId: string;
  description: string;
  vendor?: string;
  purchaseReason?: string;
  paymentMethod?: PaymentMethod;
  paidBy: PaidBy;
}

export type ExpenseUpdate = Partial<Omit<ExpenseInput, "paidBy">>;

/** Leitura de uma foto de nota (docs/ocr.md): uma SUGESTAO para o formulario, campo a campo e com a certeza de cada um (0 a 1). */
export interface OcrSuggestion {
  amountCents: number | null;
  /** YYYY-MM-DD */
  occurredOn: string | null;
  vendor: string | null;
  documentNumber: string | null;
  confidence: { amount: number; date: number; vendor: number; document: number };
  model: string;
  elapsedMs: number;
}

// ---------------------------------------------------------------- REAL: solicitacoes (docs/staff-requests.md)

export type RequestCategory = "SUPPLIES" | "MAINTENANCE" | "EVENT" | "FINANCE" | "OTHER";
export type RequestStatus = "OPEN" | "IN_PROGRESS" | "RESOLVED" | "CANCELLED";

export interface RequestPhoto {
  id: string;
  fileName: string;
  contentType: string;
  sizeBytes: number;
  uploadedByUserId: string;
  createdAt: string;
}

/** Pedido de um funcionario a gestao. A API devolve so o id de quem escreveu (nao o nome). */
export interface StaffRequestSummary {
  id: string;
  category: RequestCategory;
  title: string;
  status: RequestStatus;
  authorUserId: string;
  attachmentsCount: number;
  createdAt: string;
  updatedAt: string;
  resolvedAt: string | null;
}

export interface StaffRequestDetail extends StaffRequestSummary {
  description: string | null;
  startedAt: string | null;
  startedByUserId: string | null;
  resolvedByUserId: string | null;
  /** O que a gestao escreveu ao resolver (o autor le). */
  resolutionNote: string | null;
  photos: RequestPhoto[];
}

export interface StaffRequestInput {
  category: RequestCategory;
  title: string;
  description?: string;
}

// ---------------------------------------------------------------- REAL: campanhas (docs/campaigns.md)

export type CampaignStatus = "DRAFT" | "ACTIVE" | "ENDED";

/** Um produto de uma campanha, como a gestao o ve. O preco e da API: o site nunca decide um total. */
export interface CampaignItem {
  id: string;
  name: string;
  description: string | null;
  priceCents: Cents;
  /** O que uma unidade custa para a APM (opcional). Medida de gestao: nao e lancamento no caixa. */
  unitCostCents: Cents | null;
  maxPerOrder: number | null;
  position: number;
  isActive: boolean;
  hasImage: boolean;
  imageVersion: number;
}

export interface CampaignSummary {
  id: string;
  title: string;
  status: CampaignStatus;
  startsOn: string | null;
  endsOn: string | null;
  hasCover: boolean;
  itemsCount: number;
  activeItemsCount: number;
  /** O que os pedidos ja pagos trouxeram: quantos e quanto (o dinheiro esta no caixa). */
  paidOrdersCount: number;
  paidCents: Cents;
  createdAt: string;
  updatedAt: string;
}

export interface CampaignDetail extends CampaignSummary {
  description: string | null;
  coverVersion: number;
  /** A familia precisa dizer o aluno e a turma ao fazer o pedido (para a gestao saber a quem entregar). */
  askStudentClass: boolean;
  items: CampaignItem[];
}

export interface CampaignInput {
  title: string;
  description?: string | null;
  startsOn?: string | null;
  endsOn?: string | null;
  askStudentClass?: boolean;
}

export interface CampaignItemInput {
  name: string;
  description?: string | null;
  priceCents: Cents;
  unitCostCents?: Cents | null;
  maxPerOrder?: number | null;
  position?: number;
}

/** Situacao do pagamento de um pedido, como o painel mostra: Pendente, Aprovado, Cancelado. */
export type OrderPaymentStatus = "PENDING" | "PAID" | "CANCELLED";
export type OrderDeliveryStatus = "PENDING" | "DELIVERED";

/** Um produto da campanha e o que os pedidos APROVADOS levaram dele. */
export interface SoldItem {
  itemId: string;
  name: string;
  unitsSold: number;
  revenueCents: Cents;
  /** Custo total do que foi vendido; nulo quando algum pedido foi feito sem custo informado. */
  costCents: Cents | null;
  costKnown: boolean;
}

/** O painel de uma campanha. Tudo calculado no servidor. */
export interface CampaignDashboard {
  campaignId: string;
  title: string;
  status: CampaignStatus;
  paidOrdersCount: number;
  pendingOrdersCount: number;
  cancelledOrdersCount: number;
  /** Arrecadado: o que os pedidos aprovados trouxeram (o mesmo numero do caixa). */
  collectedCents: Cents;
  unitsSold: number;
  costCents: Cents;
  /** Falso quando alguma unidade vendida nao tem custo: ai nao ha lucro para mostrar. */
  costComplete: boolean;
  profitCents: Cents | null;
  deliveredOrdersCount: number;
  toDeliverOrdersCount: number;
  items: SoldItem[];
}

export interface OrderLineView {
  itemName: string;
  quantity: number;
  unitPriceCents: Cents;
}

export interface CampaignOrder {
  orderId: string;
  referenceCode: number;
  createdAt: string;
  guardianName: string | null;
  studentName: string | null;
  className: string | null;
  amountCents: Cents;
  paymentStatus: OrderPaymentStatus;
  /** So um pedido aprovado tem entrega para acompanhar. */
  deliveryStatus: OrderDeliveryStatus | null;
  deliveryChangedAt: string | null;
  lines: OrderLineView[];
}

export interface CampaignOrderPage {
  items: CampaignOrder[];
  total: number;
  limit: number;
  offset: number;
}

export interface OrderFilters {
  payment?: OrderPaymentStatus;
  delivery?: OrderDeliveryStatus;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface DeliveryResult {
  changed: number;
  unchanged: number;
  skipped: number;
}

/** O que a familia ve (docs/campaigns.md): so produtos ativos, com o preco de hoje. */
export interface PublicCampaignItem {
  id: string;
  name: string;
  description: string | null;
  priceCents: Cents;
  maxPerOrder: number | null;
  hasImage: boolean;
  imageVersion: number;
}

export interface PublicCampaignSummary {
  id: string;
  title: string;
  description: string | null;
  endsOn: string | null;
  hasCover: boolean;
  coverVersion: number;
  itemsCount: number;
  /** O pedido precisa do nome do aluno e da turma. */
  askStudentClass: boolean;
}

export interface PublicCampaign extends PublicCampaignSummary {
  items: PublicCampaignItem[];
}

/** O carrinho: QUAIS produtos e QUANTOS. Nunca um preco nem um total: o servidor le os precos. */
export interface OrderLine {
  itemId: string;
  quantity: number;
}

export interface CreateOrderInput {
  lines: OrderLine[];
  identification: IdentificationValues;
}

// ---------------------------------------------------------------- REAL: fechamento mensal (docs/statement.md)

/** Fechamento do mes: numeros de statement_summary congelados, mais o codigo de verificacao. */
export interface Closing {
  id: string;
  schoolId: string;
  period: string;
  periodStart: string;
  periodEnd: string;
  timezone: string;
  openingBalanceCents: Cents;
  contributionsInCents: Cents;
  otherInCents: Cents;
  refundsInCents: Cents;
  totalInCents: Cents;
  expensesOutCents: Cents;
  reimbursementsOutCents: Cents;
  totalOutCents: Cents;
  /** Saldo PRINCIPAL: em caixa. */
  closingBalanceCents: Cents;
  pendingReimbursementsCents: Cents;
  /** Saldo SECUNDARIO. */
  closingAfterPendingCents: Cents;
  entriesCount: number;
  /** Codigo de verificacao do fechamento. */
  entriesHash: string;
  bankBalanceReportedCents: Cents | null;
  /** Banco menos caixa. */
  bankDifferenceCents: Cents | null;
  closedAt: string;
  reportRef: string | null;
  /** Preenchido = fechamento REABERTO (sem PDF). */
  reopenedAt: string | null;
  /** Texto livre que a gestao escreveu: so para quem pode ver (o viewer nao recebe). */
  reopenReason: string | null;
}

export interface ClosingVerification {
  closingId: string;
  verified: boolean;
  entriesHash: string;
}
