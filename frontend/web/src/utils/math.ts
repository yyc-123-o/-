import MarkdownIt from "markdown-it";
import katex from "katex";
import "katex/dist/katex.min.css";

function mathPlugin(md: MarkdownIt): void {
  md.inline.ruler.before("escape", "math_inline", (state, silent) => {
    const start = state.pos;
    if (state.src[start] !== "$" || state.src[start + 1] === "$") return false;
    let end = start + 1;
    while (end < state.posMax) {
      if (state.src[end] === "\\") {
        end += 2;
        continue;
      }
      if (state.src[end] === "$") break;
      end += 1;
    }
    if (end >= state.posMax || end === start + 1) return false;
    if (silent) return true;
    const token = state.push("math_inline", "span", 0);
    token.content = state.src.slice(start + 1, end);
    token.markup = "$";
    state.pos = end + 1;
    return true;
  });

  md.block.ruler.before("paragraph", "math_block", (state, startLine, endLine, silent) => {
    const start = state.bMarks[startLine] + state.tShift[startLine];
    const firstLine = state.src.slice(start, state.eMarks[startLine]).trim();
    if (firstLine !== "$$") return false;
    let nextLine = startLine + 1;
    while (nextLine < endLine) {
      const lineStart = state.bMarks[nextLine] + state.tShift[nextLine];
      const line = state.src.slice(lineStart, state.eMarks[nextLine]).trim();
      if (line === "$$") break;
      nextLine += 1;
    }
    if (nextLine >= endLine) return false;
    if (silent) return true;
    const contentStart = state.eMarks[startLine] + 1;
    const contentEnd = state.bMarks[nextLine];
    const token = state.push("math_block", "div", 0);
    token.block = true;
    token.content = state.src.slice(contentStart, contentEnd).trim();
    token.map = [startLine, nextLine + 1];
    token.markup = "$$";
    state.line = nextLine + 1;
    return true;
  });

  md.renderer.rules.math_inline = (tokens, index) =>
    katex.renderToString(tokens[index].content, {
      displayMode: false,
      throwOnError: false,
      strict: "ignore",
    });
  md.renderer.rules.math_block = (tokens, index) =>
    `<div class="katex-display">${katex.renderToString(tokens[index].content, {
      displayMode: true,
      throwOnError: false,
      strict: "ignore",
    })}</div>`;
}

const markdown = new MarkdownIt({ html: false, breaks: true }).use(mathPlugin);

/** Render declared TeX delimiters without rewriting valid lesson formulas. */
export function normalizeMath(value: string, promoteComplex = true): string {
  const source = String(value);
  const segments = source.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)/g);
  return segments.map((segment, index) => {
    if (index % 2 === 1) {
      return segment;
    }
    const protectedMath: string[] = [];
    const protectedText = segment.replace(/\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\n])+\$/g, (part) => {
      const placeholder = `\uE000${protectedMath.length}\uE001`;
      protectedMath.push(part);
      return placeholder;
    });
    const normalized = normalizeLegacyMath(protectedText)
      .replace(/\\\(([^\n]*?)\\\)/g, (_match, body: string) => "$" + body + "$")
      .replace(/\\\[([\s\S]*?)\\\]/g, (_match, body: string) => promoteComplex ? `\n\n$$\n${body.trim()}\n$$\n\n` : "$" + body + "$");
    const restored = normalized
      .replace(/\u0000(\d+)\u0000/g, (_match, placeholderIndex: string) => protectedMath[Number(placeholderIndex)])
      .replace(/\uE000(\d+)\uE001/g, (_match, placeholderIndex: string) => protectedMath[Number(placeholderIndex)]);
    return promoteComplex ? normalizeDisplayMath(restored) : restored;
  }).join("");
}

/** Markdown-it-katex requires display delimiters to occupy their own paragraph. */
function normalizeDisplayMath(value: string): string {
  return value.replace(/\$\$([\s\S]*?)\$\$/g, (_match, body: string) =>
    `\n\n$$\n${body.trim()}\n$$\n\n`,
  );
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
