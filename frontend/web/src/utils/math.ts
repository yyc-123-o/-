import MarkdownIt from "markdown-it";
import markdownItKatex from "markdown-it-katex";
import "katex/dist/katex.min.css";

const markdown = new MarkdownIt({ html: false, breaks: true }).use(markdownItKatex);

/** Convert common TeX delimiters while leaving executable code fences untouched. */
export function normalizeMath(value: string, promoteComplex = true): string {
  const source = String(value);
  const segments = source.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)/g);
  return segments.map((segment, index) => {
    if (index % 2 === 1) {
      const textFence = segment.match(/^(?:```|~~~)text\s*\n([\s\S]*?)\n(?:```|~~~)$/i);
      return textFence ? `\n\n$$\n${normalizeLegacyMath(textFence[1])}\n$$\n\n` : segment;
    }
    const normalized = normalizeBareTex(normalizeLegacyMath(segment))
      .replace(/\\\(([^\n]*?)\\\)/g, (_match, body: string) => "$" + body + "$")
      .replace(/\\\[([\s\S]*?)\\\]/g, (_match, body: string) => promoteComplex ? "\n\n$$\n" + body + "\n$$\n\n" : "$" + body + "$");
    return promoteComplex ? promoteComplexMath(normalized) : normalized;
  }).join("");
}

/** Keep tall TeX constructs out of paragraph line boxes. */
function promoteComplexMath(value: string): string {
  const blockSafe = value.replace(/\$\$([\s\S]*?)\$\$/g, (_match, body: string) =>
    `\n\n$$\n${body.trim()}\n$$\n\n`,
  );
  return blockSafe.replace(/\$(?!\$)([^$\n]*?)\$/g, (match, body: string) => {
    if (!/(?:\\begin\{|\\end\{|\\matrix|\\frac|\\sum|\\prod|\\left|\\right)/.test(body)) {
      return match;
    }
    return `\n\n$$\n${body}\n$$\n\n`;
  });
}

/** Recover common TeX commands emitted without dollar delimiters. */
function normalizeBareTex(value: string): string {
  const protectedParts: string[] = [];
  const protectedText = value.replace(/\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\n])+\$/g, (part) => {
    const index = protectedParts.push(part) - 1;
    return `\u0001${index}\u0002`;
  });
  const normalized = protectedText
    .replace(
      /(?<![$\\])((?:\\(?:mathbb|mathbf|mathrm|mathcal)\{[^{}\n]+\}(?:[_^][A-Za-z0-9{}]+)?)(?:\s*(?:=|∈|\\(?:in|dots|cdot|times)|[A-Za-z0-9_{}\[\],+\-*/^]))*)/g,
      (_match, body: string) => `$${body.trim()}$`,
    );
  const formulaParts: string[] = [];
  const formulaSafe = normalized.replace(/\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\n])+\$/g, (part) => {
    const index = formulaParts.push(part) - 1;
    return `\u0003${index}\u0004`;
  });
  const withCommands = formulaSafe.replace(
      /(?<![$\\])(\\(?:alpha|beta|gamma|theta|lambda|mu|sigma|in|notin|cdot|times|dots)\b)/g,
      (_match, command: string) => `$${command}$`,
    );
  return withCommands
    .replace(/\u0003(\d+)\u0004/g, (_match, index: string) => formulaParts[Number(index)])
    .replace(/\u0001(\d+)\u0002/g, (_match, index: string) => protectedParts[Number(index)]);
}

function normalizeLegacyMath(value: string): string {
  let result = value;
  const protectedMath: string[] = [];
  result = result.replace(
    /\bfloor\(\(([^()\n]+)\)\/([^()\n]+)\)\s*\+\s*1/g,
    (_match, numerator: string, denominator: string) => {
      const formula = `$\\left\\lfloor\\frac{${numerator.replace(/[×x]/g, "\\times")}}{${denominator}}\\right\\rfloor + 1$`;
      protectedMath.push(formula);
      return `\u0000${protectedMath.length - 1}\u0000`;
    },
  );
  result = result.replace(
    /\bfloor\(([^()\n]+)\)\s*\+\s*1/g,
    (_match, body: string) => {
      const formula = `$\\left\\lfloor ${body.replace(/[×x]/g, "\\times")} \\right\\rfloor + 1$`;
      protectedMath.push(formula);
      return `\u0000${protectedMath.length - 1}\u0000`;
    },
  );
  result = result.replace(
    /(?<![$\\\w])(\d+(?:\s*[×x]\s*\d+)+)(?![$\w])/g,
    (_match, expression: string) =>
      `$${expression.replace(/[×x]/g, "\\times")}$`,
  );
  result = result.replace(
    /(?<![$\\\w])(\d+)\s*[×x]\s*(padding|stride|kernel(?:_size)?)(?![$\w])/gi,
    (_match, number: string, parameter: string) =>
      `$${number}\\times\\mathrm{${parameter.replace("_", "\\_")}}$`,
  );
  return result.replace(/\u0000(\d+)\u0000/g, (_match, index: string) => protectedMath[Number(index)]);
}

export function renderMarkdown(value: string): string {
  return markdown.render(normalizeMath(value));
}

export function renderInlineMath(value: string): string {
  return markdown.renderInline(normalizeMath(value, false));
}
