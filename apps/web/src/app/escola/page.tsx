import type { Metadata } from "next";
import Link from "next/link";
import { AuthShell } from "@/components/auth/AuthShell";
import { FindSchoolForm } from "@/components/portal/FindSchoolForm";

export const metadata: Metadata = { title: "Contribuir com a APM" };

export default function FindSchoolPage() {
  return (
    <AuthShell title="Contribuir com a APM" eyebrow="Sem login, em um minuto">
      <p className="mt-3 text-body text-ink-2">
        Digite o código da sua escola. Ele é a última parte do link que a escola enviou, por exemplo <span className="font-semibold text-ink">demo-aurora</span>.
      </p>
      <FindSchoolForm />
      <p className="mt-6 text-center text-foot text-ink-2">
        <Link href="/login" className="font-semibold text-brand-800 underline underline-offset-2">
          Voltar para a entrada
        </Link>
      </p>
    </AuthShell>
  );
}
