import axe from "axe-core";

/** Executa o axe-core (regras WCAG 2.0/2.1 A e AA) e devolve as violações. */
export async function axeViolations(container: Element) {
  const results = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
    // jsdom não calcula estilos/layout reais; contraste é validado manualmente pelos tokens.
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.map((v) => `${v.id}: ${v.help}`);
}
