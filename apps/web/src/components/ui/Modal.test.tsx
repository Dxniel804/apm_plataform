import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>Abrir</button>
      <Modal
        open={open}
        onClose={() => {
          onClose();
          setOpen(false);
        }}
        label="Janela de teste"
      >
        <button>Primeiro</button>
        <button>Ultimo</button>
      </Modal>
    </div>
  );
}

afterEach(() => {
  document.documentElement.style.overflow = "";
});

describe("Modal", () => {
  it("abre como dialog modal com nome acessivel, leva o foco para a janela e trava a rolagem da pagina", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abrir" }));
    const dialog = screen.getByRole("dialog", { name: "Janela de teste" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();
    expect(document.documentElement.style.overflow).toBe("hidden");
  });

  it("Esc fecha, devolve o foco a quem abriu e solta a rolagem", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Harness onClose={onClose} />);
    const opener = screen.getByRole("button", { name: "Abrir" });
    await user.click(opener);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
    expect(document.documentElement.style.overflow).toBe("");
  });

  it("o foco fica preso na janela: Tab no ultimo volta ao primeiro e Shift+Tab no primeiro vai ao ultimo", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));
    const first = screen.getByRole("button", { name: "Primeiro" });
    const last = screen.getByRole("button", { name: "Ultimo" });
    await user.tab();
    expect(first).toHaveFocus();
    await user.tab();
    expect(last).toHaveFocus();
    await user.tab();
    expect(first).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
  });

  it("clicar no fundo fecha; clicar dentro da janela nao", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Harness onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));
    await user.click(screen.getByRole("button", { name: "Primeiro" }));
    expect(onClose).not.toHaveBeenCalled();
    const backdrop = screen.getByRole("dialog").parentElement!;
    await user.pointer({ keys: "[MouseLeft]", target: backdrop });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("Modal aninhado (a camera abre por cima do formulario)", () => {
  function Nested({ outerClose, innerClose }: { outerClose: () => void; innerClose: () => void }) {
    const [outer, setOuter] = useState(true);
    const [inner, setInner] = useState(true);
    return (
      <div>
        <Modal open={outer} onClose={() => { outerClose(); setOuter(false); }} label="De baixo">
          <button>Botao de baixo</button>
        </Modal>
        <Modal open={inner} onClose={() => { innerClose(); setInner(false); }} label="De cima">
          <button>Botao de cima</button>
          <button>Outro de cima</button>
        </Modal>
      </div>
    );
  }

  it("Esc fecha so a janela de cima; a de baixo continua aberta e o proximo Esc a fecha", async () => {
    const outerClose = vi.fn();
    const innerClose = vi.fn();
    const user = userEvent.setup();
    render(<Nested outerClose={outerClose} innerClose={innerClose} />);

    await user.keyboard("{Escape}");
    expect(innerClose).toHaveBeenCalledTimes(1);
    expect(outerClose).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "De cima" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "De baixo" })).toBeInTheDocument();
    expect(document.documentElement.style.overflow).toBe("hidden"); // a pagina segue travada pela janela de baixo

    await user.keyboard("{Escape}");
    expect(outerClose).toHaveBeenCalledTimes(1);
    expect(document.documentElement.style.overflow).toBe("");
  });

  it("o Tab fica na janela de cima: a de baixo nao rouba o foco", async () => {
    const user = userEvent.setup();
    render(<Nested outerClose={() => {}} innerClose={() => {}} />);
    const first = screen.getByRole("button", { name: "Botao de cima" });
    const last = screen.getByRole("button", { name: "Outro de cima" });

    await user.tab();
    expect(first).toHaveFocus();
    await user.tab();
    expect(last).toHaveFocus();
    await user.tab();
    expect(first).toHaveFocus();
  });
});
