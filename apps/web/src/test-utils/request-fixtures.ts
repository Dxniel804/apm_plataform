import type { RequestPhoto, StaffRequestDetail, StaffRequestSummary } from "@/lib/api/types";

/** Dados FALSOS para os testes das solicitacoes. snake_case = formato da API. */
export const REQUEST_AUTHOR_ID = "7ff63d82-d8f0-40b3-9f27-778469d4c711";
export const REQUEST_MANAGER_ID = "e25e2070-9cd7-4294-9eb6-8e0a0a00df00";
export const REQUEST_ID = "9d4d8c0e-6a43-4a7f-8c5e-0d5a8f0a1b11";

export function requestSummaryBody(overrides: Record<string, unknown> = {}) {
  return {
    id: REQUEST_ID,
    category: "SUPPLIES",
    title: "Faltou papel higiênico",
    status: "OPEN",
    author_user_id: REQUEST_AUTHOR_ID,
    attachments_count: 1,
    created_at: "2026-10-06T13:41:42Z",
    updated_at: "2026-10-06T13:41:42Z",
    resolved_at: null,
    ...overrides,
  };
}

export function photoBody(overrides: Record<string, unknown> = {}) {
  return {
    id: "a1111111-1111-4111-8111-111111111111",
    file_name: "foto.jpg",
    content_type: "image/jpeg",
    size_bytes: 20480,
    sha256: "f".repeat(64),
    uploaded_by_user_id: REQUEST_AUTHOR_ID,
    created_at: "2026-10-06T13:45:00Z",
    ...overrides,
  };
}

export function requestDetailBody(overrides: Record<string, unknown> = {}) {
  return {
    ...requestSummaryBody(),
    description: "Acabou no banheiro do segundo andar.",
    started_at: null,
    started_by_user_id: null,
    resolved_by_user_id: null,
    resolution_note: null,
    attachments: [photoBody()],
    ...overrides,
  };
}

export function requestSummary(overrides: Partial<StaffRequestSummary> = {}): StaffRequestSummary {
  return {
    id: REQUEST_ID,
    category: "SUPPLIES",
    title: "Faltou papel higiênico",
    status: "OPEN",
    authorUserId: REQUEST_AUTHOR_ID,
    attachmentsCount: 1,
    createdAt: "2026-10-06T13:41:42Z",
    updatedAt: "2026-10-06T13:41:42Z",
    resolvedAt: null,
    ...overrides,
  };
}

export function requestPhoto(overrides: Partial<RequestPhoto> = {}): RequestPhoto {
  return {
    id: "a1111111-1111-4111-8111-111111111111",
    fileName: "foto.jpg",
    contentType: "image/jpeg",
    sizeBytes: 20480,
    uploadedByUserId: REQUEST_AUTHOR_ID,
    createdAt: "2026-10-06T13:45:00Z",
    ...overrides,
  };
}

export function requestDetail(overrides: Partial<StaffRequestDetail> = {}): StaffRequestDetail {
  return {
    ...requestSummary(),
    description: "Acabou no banheiro do segundo andar.",
    startedAt: null,
    startedByUserId: null,
    resolvedByUserId: null,
    resolutionNote: null,
    photos: [requestPhoto()],
    ...overrides,
  };
}
