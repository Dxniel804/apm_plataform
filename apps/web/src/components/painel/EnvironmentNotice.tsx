/**
 * Aviso fixo do ambiente de demonstracao (docs/adr-ambiente-sandbox.md): a organizacao esta em
 * `sandbox`, entao os dados desta escola sao de demonstracao. Some quando ela vai para producao.
 * Nao e um erro: texto sobrio, sem cor de alerta. Ainda NAO promete "nenhum pagamento real": isso so
 * entra quando o backend recusar o Pix real em sandbox (a parte seguinte do ADR).
 */
export function EnvironmentNotice() {
  return (
    <p
      role="status"
      className="mx-3 mb-3 flex items-start gap-2.5 rounded-[var(--r-xl)] bg-white px-5 py-3 text-foot leading-snug text-ink-2 sm:mx-5 lg:ml-0 lg:mr-5"
    >
      <span aria-hidden="true" className="mt-[0.4em] size-1.5 shrink-0 rounded-full bg-info" />
      <span>
        <b className="font-medium text-ink">Você está no ambiente de demonstração.</b> Os dados desta escola são de demonstração.
      </span>
    </p>
  );
}
