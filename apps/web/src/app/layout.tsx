import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { connection } from "next/server";
import { MotionGate } from "@/components/ui/MotionGate";
import "./globals.css";

// 42dot Sans (SIL OFL, ver fonts/OFL.txt): fonte variavel do Figma, servida pelo proprio site (CSP: font-src 'self').
const sans = localFont({
  src: "./fonts/42dot-sans-latin.woff2",
  weight: "300 800",
  display: "swap",
  variable: "--font-42dot",
});

export const metadata: Metadata = {
  title: { default: "APM Digital", template: "%s · APM Digital" },
  description:
    "Contribuições da APM por Pix, com comprovante, e a prestação de contas da gestão no mesmo lugar.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light",
  themeColor: "#ffffff",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // A CSP usa um nonce por requisicao (src/proxy.ts): as paginas precisam ser dinamicas.
  await connection();
  return (
    <html lang="pt-BR" className={sans.variable}>
      <body>
        <a
          href="#conteudo"
          className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-brand-800 focus:px-4 focus:py-3 focus:text-sub focus:font-semibold focus:text-white"
        >
          Ir para o conteúdo
        </a>
        <MotionGate />
        {children}
      </body>
    </html>
  );
}
