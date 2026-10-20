import type { PddeEconomic, PddeProgram } from "@/lib/api/pdde";

/**
 * O que foi comprado, em palavras comuns, e se isso e capital (bem que dura) ou custeio (consumo, servico).
 * Quem classifica escolhe o item; o site deduz custeio ou capital. A lista e uma proposta: os usos vem do art. 4
 * da Res. CD/FNDE 15/2021 (material permanente, material de consumo, pequenos reparos, avaliacao de aprendizagem,
 * projeto pedagogico, atividades educacionais) e deve ser conferida contra a resolucao de cada programa.
 */
export interface PddeObject {
  label: string;
  economic: PddeEconomic;
  /** Palavras (sem acento, minusculas) que, no texto do extrato, sugerem este item. */
  words: string[];
}

export const PDDE_OBJECTS: readonly PddeObject[] = [
  { label: "Móveis (mesa, cadeira, armário)", economic: "CAPITAL", words: ["mesa", "cadeira", "armario", "estante", "carteira", "mobili"] },
  { label: "Eletro ou eletrônico (ventilador, geladeira, TV)", economic: "CAPITAL", words: ["ventilador", "geladeira", "freezer", "televis", "bebedouro", "microondas", "fogao", "ar condicionado", "caixa de som"] },
  { label: "Computador, impressora ou tablet", economic: "CAPITAL", words: ["computador", "notebook", "impressora", "tablet", "projetor", "roteador"] },
  { label: "Máquina ou equipamento", economic: "CAPITAL", words: ["maquina", "equipamento", "ferramenta"] },
  { label: "Pequeno reparo ou manutenção", economic: "CUSTEIO", words: ["reparo", "manutenc", "conserto", "pintura", "eletricista", "encanador"] },
  { label: "Serviço (mão de obra, frete, instalação)", economic: "CUSTEIO", words: ["servico", "frete", "instalac", "mao de obra"] },
  { label: "Material pedagógico", economic: "CUSTEIO", words: ["pedagog", "livro", "jogo", "brinquedo"] },
  { label: "Atividade ou projeto pedagógico", economic: "CUSTEIO", words: ["projeto", "atividade", "oficina"] },
  { label: "Avaliação de aprendizagem", economic: "CUSTEIO", words: ["avaliac", "simulado"] },
  { label: "Material de consumo (papel, limpeza, escritório)", economic: "CUSTEIO", words: ["papel", "papelaria", "limpeza", "material", "caneta", "toner", "cartucho", "higiene"] },
];

/** Minusculas e sem acento, para comparar o texto do extrato. */
export function plain(text: string): string {
  return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

/** O item que o texto de uma saida do extrato sugere, ou null. */
export function suggestObject(memo: string): PddeObject | null {
  const text = plain(memo);
  return PDDE_OBJECTS.find((o) => o.words.some((w) => text.includes(w))) ?? null;
}

export interface CreditSuggestion {
  kind: "TRANSFER" | "YIELD";
  program: PddeProgram | null;
  economic: PddeEconomic | null;
}

const PROGRAM_WORDS: [PddeProgram, string][] = [
  ["BASICO", "basico"],
  ["EQUIDADE", "equidade"],
  ["QUALIDADE", "qualidade"],
  ["CONECTADO", "conectad"],
];

/**
 * O que o texto de uma entrada do extrato diz: repasse ou rendimento, o programa e custeio ou capital. O FNDE
 * escreve isso na propria linha ("CREDITO FNDE PDDE BASICO CAPITAL"). O que o texto nao diz fica null.
 */
export function suggestCredit(memo: string): CreditSuggestion {
  const text = plain(memo);
  const program = PROGRAM_WORDS.find(([, w]) => text.includes(w))?.[0] ?? null;
  const economic: PddeEconomic | null = text.includes("capital") ? "CAPITAL" : text.includes("custeio") ? "CUSTEIO" : null;
  const kind = text.includes("rendimento") || text.includes("aplicacao") ? "YIELD" : "TRANSFER";
  return { kind, program, economic };
}
