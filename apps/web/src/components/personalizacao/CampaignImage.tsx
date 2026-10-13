"use client";

import { useEffect, useState } from "react";
import { ImageIcon } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { useObjectUrl } from "@/lib/hooks/useObjectUrl";

interface Props {
  schoolId: string;
  campaignId: string;
  /** Sem `itemId`, a capa da campanha; com ele, a imagem do produto. */
  itemId?: string;
  /** A API diz se ha imagem: sem ela nem se pergunta. */
  present: boolean;
  /** Muda quando a imagem e trocada: busca de novo. */
  version: number;
  alt: string;
  className?: string;
}

/**
 * Imagem de uma campanha ou de um produto para a GESTAO: baixada pela API com a sessao (ela ve tambem o
 * rascunho, que ainda nao e publico). Sem imagem, ou enquanto baixa, mostra o espaco vazio.
 */
export function CampaignImage({ schoolId, campaignId, itemId, present, version, alt, className = "" }: Props) {
  const key = `${schoolId}|${campaignId}|${itemId ?? ""}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; blob: Blob | null } | null>(null);
  useEffect(() => {
    if (!present) return;
    let cancelled = false;
    void api.campaigns.image(schoolId, campaignId, itemId).then((result) => {
      if (!cancelled) setLoaded({ key, blob: result.ok ? result.data.blob : null });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, campaignId, itemId, present, key]);

  const url = useObjectUrl(present && loaded?.key === key ? loaded.blob : null);
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element -- imagem baixada pela API com a sessao (blob:), sem URL publica
    return <img src={url} alt={alt} className={`object-cover ${className}`} />;
  }
  return (
    <span aria-hidden="true" className={`grid place-items-center bg-info-soft text-brand-800 ${className}`}>
      <ImageIcon size={28} />
    </span>
  );
}
