import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RECEIPT } from "@/test-utils/public-fixtures";
import { ReceiptCard } from "./ReceiptCard";

describe("ReceiptCard", () => {
  it("contribuicao comum: sem lista de produtos e com o titulo de sempre", () => {
    render(<ReceiptCard receipt={RECEIPT} />);
    expect(screen.getByText("Comprovante de contribuição")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Produtos do pedido" })).not.toBeInTheDocument();
  });

  it("pedido de campanha: o titulo da campanha e o que foi comprado, como foi comprado, e o valor e a soma", () => {
    const receipt = {
      ...RECEIPT,
      amountCents: 2250,
      campaignTitle: "Festa Junina",
      items: [
        { name: "Cachorro-quente", unitPriceCents: 800, quantity: 2 },
        { name: "Pamonha", unitPriceCents: 650, quantity: 1 },
      ],
    };
    render(<ReceiptCard receipt={receipt} />);

    expect(screen.getByText("Comprovante de pedido · Festa Junina")).toBeInTheDocument();
    const lines = within(screen.getByRole("list", { name: "Produtos do pedido" })).getAllByRole("listitem");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveTextContent("2 × Cachorro-quente");
    expect(lines[0]).toHaveTextContent("R$ 16,00");
    expect(lines[1]).toHaveTextContent("1 × Pamonha");
    expect(lines[1]).toHaveTextContent("R$ 6,50");
    expect(screen.getAllByText("R$ 22,50").length).toBeGreaterThan(0); // o valor do comprovante
  });
});
