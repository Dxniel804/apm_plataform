import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { PublicLink, SchoolIdentity, SchoolSettings } from "@/lib/api/types";
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

const IDENTITY: SchoolIdentity = {
  name: "Escola Aurora",
  slug: "demo-aurora",
  url: "https://doar.exemplo.com.br/escola/demo-aurora",
  slugChanges: 0,
  freeChangesLeft: 2,
  slugLockedUntil: null,
  linkActive: true,
  previousSlugs: [],
};

beforeEach(() => {
  saveBlob.mockReset();
  vi.spyOn(api.schoolSettings, "identity").mockResolvedValue({ ok: true, data: IDENTITY });
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

  it("qualquer perfil troca a propria senha ali mesmo, sem janela", () => {
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={["expenses:submit"]} />);
    expect(screen.getByRole("heading", { name: "Alterar senha" })).toBeInTheDocument();
    expect(screen.getByLabelText("Senha atual")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancelar" })).not.toBeInTheDocument();
  });
});

describe("Nome e endereco da escola", () => {
  it("mostra o nome, o endereco, a previa do link e quantas trocas sem espera restam", async () => {
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    expect(await screen.findByLabelText("Nome da escola")).toHaveValue("Escola Aurora");
    expect(screen.getByLabelText("Endereço do link")).toHaveValue("demo-aurora");
    expect(screen.getByText(/Fica assim: https:\/\/doar\.exemplo\.com\.br\/escola\/demo-aurora/)).toBeInTheDocument();
    expect(screen.getByText(/mais 2 vezes sem espera/)).toBeInTheDocument();
    // a promessa antiga ("o endereco nao pode mudar") nao existe mais
    expect(screen.queryByText(/não pode mudar/)).not.toBeInTheDocument();
  });

  it("o nome muda direto, sem confirmacao, e manda so o nome", async () => {
    const update = vi.spyOn(api.schoolSettings, "updateIdentity").mockResolvedValue({ ok: true, data: { ...IDENTITY, name: "Escola Ipê" } });
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const name = await screen.findByLabelText("Nome da escola");
    await user.clear(name);
    await user.type(name, "Escola Ipê");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(update).toHaveBeenCalledWith(SCHOOL_ID, { name: "Escola Ipê" }));
    expect(await screen.findByText("Salvo.")).toBeInTheDocument();
  });

  it("trocar o endereco pede confirmacao (conta como uma troca) e so entao envia", async () => {
    const update = vi.spyOn(api.schoolSettings, "updateIdentity").mockResolvedValue({ ok: true, data: { ...IDENTITY, slug: "escola-ipe", slugChanges: 1, freeChangesLeft: 1, previousSlugs: ["demo-aurora"] } });
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const slug = await screen.findByLabelText("Endereço do link");
    await user.clear(slug);
    await user.type(slug, "Escola-Ipe");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(update).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Trocar o endereço para https://doar.exemplo.com.br/escola/escola-ipe");
    await user.click(screen.getByRole("button", { name: "Confirmar a troca" }));
    await waitFor(() => expect(update).toHaveBeenCalledWith(SCHOOL_ID, { slug: "escola-ipe" })); // minusculas
  });

  it("endereco mal formado: avisa na hora e nao deixa salvar", async () => {
    const update = vi.spyOn(api.schoolSettings, "updateIdentity");
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const slug = await screen.findByLabelText("Endereço do link");
    await user.clear(slug);
    await user.type(slug, "a b");
    expect(screen.getByText(/Use de 3 a 40 caracteres/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
    expect(update).not.toHaveBeenCalled();
  });

  it("depois das duas trocas o campo fica travado, diz a data, e o nome continua editavel", async () => {
    vi.spyOn(api.schoolSettings, "identity").mockResolvedValue({
      ok: true,
      data: { ...IDENTITY, slugChanges: 2, freeChangesLeft: 0, slugLockedUntil: "2026-11-01T12:00:00Z", previousSlugs: ["a-antiga", "b-antiga"] },
    });
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    expect(await screen.findByLabelText("Endereço do link")).toBeDisabled();
    expect(screen.getByLabelText("Nome da escola")).toBeEnabled();
    expect(screen.getByText(/Você poderá trocá-lo de novo em/)).toHaveTextContent("01/11/2026");
    expect(screen.getByText(/a-antiga, b-antiga/)).toBeInTheDocument();
  });

  it("endereco de outra escola: a frase certa; e sem conta de recebimento avisa que o link ainda nao abre", async () => {
    vi.spyOn(api.schoolSettings, "identity").mockResolvedValue({ ok: true, data: { ...IDENTITY, linkActive: false } });
    vi.spyOn(api.schoolSettings, "updateIdentity").mockResolvedValue({ ok: false, error: { kind: "problem", status: 409, code: "slug_taken" } });
    const user = userEvent.setup();
    render(<SettingsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    expect(await screen.findByText(/só abre para as famílias depois que a conta de recebimento/)).toBeInTheDocument();
    const slug = screen.getByLabelText("Endereço do link");
    await user.clear(slug);
    await user.type(slug, "escola-sol");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await user.click(screen.getByRole("button", { name: "Confirmar a troca" }));
    expect(await screen.findByText(/já é de outra escola/)).toBeInTheDocument();
  });
});
