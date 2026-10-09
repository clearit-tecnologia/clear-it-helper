import type { Metadata } from "next";

import { DocumentsScreen } from "@/components/documents/documents-screen";

export const metadata: Metadata = { title: "Documentos" };

export default function DocumentsPage() {
  return <DocumentsScreen />;
}
