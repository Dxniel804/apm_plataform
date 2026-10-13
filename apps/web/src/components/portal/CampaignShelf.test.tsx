import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CAMPAIGN_ID, publicSummary } from "@/test-utils/campaign-fixtures";
import { CampaignShelf } from "./CampaignShelf";

describe("CampaignShelf", () => {
  it("sem campanhas a venda nao desenha nada", () => {
    const { container } = render(<CampaignShelf slug="demo-aurora" campaigns={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("um cartao por campanha: titulo, texto, quantidade de produtos, prazo e o link da pagina dela", () => {
    render(<CampaignShelf slug="demo-aurora" campaigns={[publicSummary({ endsOn: "2026-06-30" }), publicSummary({ id: "outra", title: "Kit escolar", itemsCount: 1, description: null })]} />);

    expect(screen.getByRole("heading", { name: "Campanhas da escola" })).toBeInTheDocument();
    const cards = screen.getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByText("Festa Junina")).toBeInTheDocument();
    expect(cards[0]).toHaveTextContent("2 produtos · até 30 de jun");
    expect(within(cards[0]!).getByRole("link")).toHaveAttribute("href", `/escola/demo-aurora/campanha/${CAMPAIGN_ID}`);
    expect(cards[1]).toHaveTextContent("1 produto");
    expect(cards[1]).not.toHaveTextContent(/\d produtos/); // singular quando e um so
  });

  it("a capa so e pedida quando a campanha tem uma; o endereco leva a versao para trocar o cache", () => {
    const { container, rerender } = render(<CampaignShelf slug="demo-aurora" campaigns={[publicSummary()]} />);
    expect(container.querySelector("img")).toBeNull();
    rerender(<CampaignShelf slug="demo-aurora" campaigns={[publicSummary({ hasCover: true, coverVersion: 3 })]} />);
    expect(container.querySelector("img")).toHaveAttribute("src", `/api/v1/public/schools/demo-aurora/campaigns/${CAMPAIGN_ID}/cover?v=3`);
    expect(container.querySelector("img")).toHaveAttribute("alt", "");
  });
});
