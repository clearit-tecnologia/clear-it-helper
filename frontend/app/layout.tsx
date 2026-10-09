import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

// Sem next/font/google: o build roda on-premises, sem acesso garantido à internet.
export const metadata: Metadata = {
  title: { default: "Clear Helper", template: "%s | Clear Helper" },
  description: "Assistente de consulta a documentos com respostas citadas.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen font-sans">
        {/* Atalho para o conteúdo (e-MAG 3.1, recomendação 1.5). */}
        <a
          href="#conteudo"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
        >
          Ir para o conteúdo
        </a>
        {children}
      </body>
    </html>
  );
}
