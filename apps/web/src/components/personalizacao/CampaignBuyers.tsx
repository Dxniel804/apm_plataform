"use client";

import { useEffect, useMemo, useState } from "react";
import { TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiResult, CampaignBuyerList } from "@/lib/api/types";
import { plain } from "@/lib/pdde-objects";
import { formatBRL } from "@/lib/money";

interface Props {
  schoolId: string;
  campaignId: string;
}

/**
 * Quem comprou: por responsavel e aluno, o que cada um levou de cada produto (so pedidos aprovados). O mesmo
 * responsavel com o mesmo aluno e somado, mesmo escrito de outro jeito. Quem soma e a API.
 */
export function CampaignBuyers({ schoolId, campaignId }: Props) {
  const key = `${schoolId}|${campaignId}`;
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<CampaignBuyerList> } | null>(null);
  const [typed, setTyped] = useState("");

  useEffect(() => {
    let cancelled = false;
    void api.campaigns.buyers(schoolId, campaignId).then((res) => !cancelled && setLoaded({ key, res }));
    return () => {
      cancelled = true;
    };
  }, [schoolId, campaignId, key]);

  const res = loaded?.key === key ? loaded.res : null;
  const all = useMemo(() => (res && res.ok ? res.data.items : []), [res]);
  const shown = useMemo(() => {
    const q = plain(typed.trim());
    if (q === "") return all;
    return all.filter((b) => plain([b.guardianName, b.studentName, b.className].filter(Boolean).join(" ")).includes(q));
  }, [all, typed]);

  if (!res) {
    return (
      <p role="status" aria-busy="true" className="text-sub text-ink-2">
        Carregando…
      </p>
    );
  }
  if (!res.ok) {
    return (
      <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
        Não foi possível carregar quem comprou. Tente de novo.
      </p>
    );
  }
  if (all.length === 0) {
    return <p className="rounded-[var(--r-lg)] border border-line px-6 py-10 text-center text-body text-ink-2">Nenhum pedido aprovado ainda.</p>;
  }

  return (
    <div className="space-y-4">
      <TextField label="Buscar responsável, aluno ou turma" name="buyers-search" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
      {shown.length === 0 ? (
        <p className="text-body text-ink-2">Ninguém com esse nome.</p>
      ) : (
        <ul aria-label="Quem comprou" className="space-y-3">
          {shown.map((b, i) => (
            <li key={`${b.guardianName}|${b.studentName}|${b.className}|${i}`} className="rounded-[var(--r-lg)] border border-line bg-white px-5 py-4 sm:px-6">
              <div className="flex flex-wrap items-start justify-between gap-x-5 gap-y-1">
                <div className="min-w-0">
                  <p className="font-semibold [overflow-wrap:anywhere]">{b.guardianName ?? "Sem nome"}</p>
                  <p className="text-sub text-ink-2">{[b.studentName, b.className].filter(Boolean).join(" · ") || "Sem aluno informado"}</p>
                </div>
                <p className="text-[1.125rem] font-bold tabular-nums text-brand-800">{formatBRL(b.amountCents)}</p>
              </div>
              <p className="mt-2 text-sub">{b.lines.map((l) => `${l.quantity} × ${l.itemName}`).join(" · ")}</p>
              <p className="mt-1 text-foot text-ink-2">
                {b.units === 1 ? "1 unidade" : `${b.units} unidades`} em {b.orders === 1 ? "1 pedido" : `${b.orders} pedidos`}
              </p>
            </li>
          ))}
        </ul>
      )}
      {!res.data.complete && <p className="text-foot text-ink-2">Há mais pedidos aprovados do que os contados aqui (os 5.000 mais recentes).</p>}
    </div>
  );
}
