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
      return textFence ? `\n$$\n${normalizeLegacyMath(textFence[1])}\n$$\n` : segment;
    }
    const normalized = normalizeLegacyMath(segment)
      .replace(/\\\(([^\n]*?)\\\)/g, (_match, body: string) => "$" + body + "$")
      .replace(/\\\[([\s\S]*?)\\\]/g, (_match, body: string) => promoteComplex ? "\n$$\n" + body + "\n$$\n" : "$" + body + "$");
    return promoteComplex ? promoteComplexMath(normalized) : normalized;
  }).join("");
}

/** Keep tall TeX constructs out of paragraph line boxes. */
function promoteComplexMath(value: string): string {
  return value.replace(/\$\$[\s\S]*?\$\$|\$(?!\$)([\s\S]*?)\$/g, (match, body?: string) => {
    if (body === undefined) return match;
    if (!/(?:\\begin\{|\\end\{|\\matrix|\\frac|\\sum|\\prod|\\left|\\right)/.test(body)) {
      return match;
    }
    return `\n$$\n${body}\n$$\n`;
  });
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
