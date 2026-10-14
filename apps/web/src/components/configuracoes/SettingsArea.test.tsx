import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { PublicLink, SchoolSettings } from "@/lib/api/types";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";

const saveBlob = vi.hoisted(() => vi.fn());
vi.mock("@/lib/download", () => ({ saveBlob }));

import { SettingsArea } from "./SettingsArea";

const MANAGER = ["school_settings:manage", "statement:read"];
const SETTINGS: SchoolSettings = {
  suggestedAmountsCents: [2000, 3000, 4000],
  allowCustomAmount: true,
  minContributionCents: 1000,
  maxContributionCents: 500000,
  freeAmountText: null,
  monthlyGoalCents: null,
  expectedContributions: null,
};
const LINK: PublicLink = { schoolName: "Escola Aurora", slug: "demo-aurora", url: "https://doar.exemplo.com.br/escola/demo-aurora" };

beforeEach(() => {
  saveBlob.mockReset();
  vi.spyOn(api.schoolSettings, "get").mockResolvedValue({ ok: true, data: SETTINGS });
  vi.spyOn(api.schoolSettings, "publicLink").mockResolvedValue({ ok: true, data: LINK });
});
afterEach(() => vi.restoreAllMocks());

describe("Configuracoes", () => {
  it("quem nao tem school_settings:manage recebe um aviso e nenhuma chamada a API", () => {
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={["campaigns:manage"]} />);
    expect(screen.getByRole("note")).toHaveTextContent("não mexe nas configurações");
    expect(api.schoolSettings.get).not.toHaveBeenCalled();
  });

  it("mostra o link da escola, o QR Code, os valores e as metas", async () => {
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);

    expect(await screen.findByTestId("school-link")).toHaveTextContent(LINK.url);
    expect(screen.getByRole("img", { name: /QR Code do link da Escola Aurora/ })).toBeInTheDocument();
    expect(screen.getByText("R$ 20,00 · R$ 30,00 · R$ 40,00")).toBeInTheDocument();
    expect(screen.getByText("Não definida")).toBeInTheDocument();
  });

  it("baixa o QR Code (SVG) e o cartaz (PDF da API)", async () => {
    vi.spyOn(api.schoolSettings, "poster").mockResolvedValue({ ok: true, data: { blob: new Blob(["%PDF"], { type: "application/pdf" }), contentType: "application/pdf" } });
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);

    await user.click(await screen.findByRole("button", { name: "Baixar o QR Code" }));
    expect(saveBlob).toHaveBeenLastCalledWith(expect.anything(), "qr-demo-aurora.svg");
    await user.click(screen.getByRole("button", { name: "Baixar o cartaz (PDF)" }));
    await waitFor(() => expect(saveBlob).toHaveBeenLastCalledWith(expect.anything(), "cartaz-demo-aurora.pdf"));
  });

  it("edita os valores sugeridos: manda so o que mudou, em centavos, e recarrega", async () => {
    const update = vi.spyOn(api.schoolSettings, "update").mockResolvedValue({ ok: true, data: { ...SETTINGS, suggestedAmountsCents: [2500, 5000] } });
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const card = (await screen.findByRole("heading", { name: "Valores da contribuição" })).closest("section")!;

    await user.click(within(card).getByRole("button", { name: "Editar" }));
    const dialog = await screen.findByRole("dialog", { name: "Valores da contribuição" });
    await user.clear(within(dialog).getByLabelText("Valor 1"));
    await user.type(within(dialog).getByLabelText("Valor 1"), "2500");
    await user.clear(within(dialog).getByLabelText("Valor 2"));
    await user.type(within(dialog).getByLabelText("Valor 2"), "5000");
    await user.clear(within(dialog).getByLabelText("Valor 3"));
    await user.click(within(dialog).getByRole("button", { name: "Salvar valores" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(SCHOOL_ID, { suggestedAmountsCents: [2500, 5000], allowCustomAmount: true, freeAmountText: null }));
    await waitFor(() => expect(api.schoolSettings.get).toHaveBeenCalledTimes(2));
  });

  it("valor fora do limite da escola e recusado na propria tela, sem chamar a API", async () => {
    const update = vi.spyOn(api.schoolSettings, "update");
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const card = (await screen.findByRole("heading", { name: "Valores da contribuição" })).closest("section")!;

    await user.click(within(card).getByRole("button", { name: "Editar" }));
    const dialog = await screen.findByRole("dialog", { name: "Valores da contribuição" });
    await user.clear(within(dialog).getByLabelText("Valor 1"));
    await user.type(within(dialog).getByLabelText("Valor 1"), "500");
    await user.click(within(dialog).getByRole("button", { name: "Salvar valores" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Cada valor vai de R$ 10,00");
    expect(update).not.toHaveBeenCalled();
  });

  it("define as metas e apaga quando o campo fica vazio", async () => {
    const update = vi.spyOn(api.schoolSettings, "update").mockResolvedValue({ ok: true, data: SETTINGS });
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const card = (await screen.findByRole("heading", { name: "Metas do mês" })).closest("section")!;

    await user.click(within(card).getByRole("button", { name: "Editar" }));
    const dialog = await screen.findByRole("dialog", { name: "Metas do mês" });
    await user.type(within(dialog).getByLabelText(/Meta de arrecadação/), "1500000");
    await user.type(within(dialog).getByLabelText(/Contribuições esperadas/), "120");
    await user.click(within(dialog).getByRole("button", { name: "Salvar metas" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(SCHOOL_ID, { monthlyGoalCents: 1500000, expectedContributions: 120 }));
  });

  it("erro da API aparece em portugues dentro da janela", async () => {
    vi.spyOn(api.schoolSettings, "update").mockResolvedValue({ ok: false, error: { kind: "network" } });
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const card = (await screen.findByRole("heading", { name: "Metas do mês" })).closest("section")!;

    await user.click(within(card).getByRole("button", { name: "Editar" }));
    const dialog = await screen.findByRole("dialog", { name: "Metas do mês" });
    await user.click(within(dialog).getByRole("button", { name: "Salvar metas" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Nada foi alterado");
  });
});
