import { ImageResponse } from "next/og";
import { getPublicSchool } from "@/lib/api/public";
import { serverFetch } from "@/lib/api/server";
import { isPlausibleSlug } from "@/lib/api/token";

export const alt = "Contribua com a APM da escola";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** A imagem da previa do link: o nome da escola e a chamada, na cor da escola. Sem dado pessoal e sem chamada externa. */
export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const result = isPlausibleSlug(slug) ? await getPublicSchool(slug, { fetchImpl: serverFetch }) : null;
  const name = result?.ok ? result.data.name : "APM Digital";
  const accent = result?.ok ? result.data.accentColor : "#0a84ff";
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", padding: 80, background: "#f3f5fa", color: "#101a3f" }}>
        <div style={{ width: 120, height: 14, borderRadius: 7, background: accent, marginBottom: 48 }} />
        <div style={{ fontSize: 40, color: "#4a5578" }}>Contribua com a APM da</div>
        <div style={{ fontSize: name.length > 34 ? 64 : 84, fontWeight: 700, lineHeight: 1.1, marginTop: 12 }}>{name}</div>
        <div style={{ fontSize: 36, color: "#4a5578", marginTop: 48 }}>Pagamento por Pix. O dinheiro vai direto para a conta da APM.</div>
      </div>
    ),
    size,
  );
}
