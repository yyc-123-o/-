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
    const normalized = normalizeBareTex(sanitizeMathDelimiters(normalizeLegacyMath(segment)), promoteComplex)
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
  // Inline formulas must stay in the surrounding sentence. Promoting a
  // fraction or summation here turns `...如 1/2...` into a centered block and
  // breaks ordered-list layout. Authors can still request display math with
  // an explicit `$$...$$` block, normalized above.
  return blockSafe;
}

/** Keep a malformed model response from swallowing the rest of a paragraph. */
function sanitizeMathDelimiters(value: string): string {
  const unescapedDollars = (value.match(/(?<!\\)\$/g) || []).length;
  return unescapedDollars % 2 === 0 ? value : value.replace(/(?<!\\)\$/g, "\\$");
}

/** Recover common TeX commands emitted without dollar delimiters. */
function normalizeBareTex(value: string, promoteComplex = true): string {
  const protectedParts: string[] = [];
  const protectedText = value.replace(/\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\n])+\$/g, (part) => {
    if (!promoteComplex && /\\begin\{/.test(part)) {
      return flattenInlineMath(part);
    }
    const index = protectedParts.push(part) - 1;
    return `\u0001${index}\u0002`;
  });
  // LLM lessons sometimes emit complete TeX environments without delimiters.
  // Protect them first so the command pass below cannot split a matrix/fraction.
  const environments: string[] = [];
  const withEnvironments = protectedText.replace(
    /\\begin\{[^{}\n]+\}[\s\S]*?\\end\{[^{}\n]+\}/g,
    (part) => {
      const index = environments.push(part) - 1;
      return `\u0005${index}\u0006`;
    },
  );
  // Keep expressions containing \text{} and function-call syntax together.
  // Splitting `\text{score}_i = \text{attention}(... )` into individual
  // atoms makes the remaining parentheses and indices render as plain text.
  const expressionParts: string[] = [];
  const withExpressions = withEnvironments
    // Keep the common generated assignment/call form as one math span.
    // This is intentionally narrow so normal prose is never swallowed.
    .replace(
      /(?<![$\\])(\\text\s*\{[^{}\n]+\}(?:[_^](?:\{[^{}\n]+\}|[A-Za-z0-9]+))?\s*=\s*\\text\s*\{[^{}\n]+\}(?:\s*\([^()\n]*\))?)/g,
      (_match, expression: string) => {
        const index = expressionParts.push(expression.trim()) - 1;
        return `\u0009${index}\u000A`;
      },
    )
    .replace(
      /(?<![$\\])((?=\\text\s*\{)(?:\\text\s*\{[^{}\n]+\}|[A-Za-z][A-Za-z0-9.]*(?:[_^](?:\{[^{}\n]+\}|[A-Za-z0-9]+))?|[_^](?:\{[^{}\n]+\}|[A-Za-z0-9+-]+)|[()[\],=+\-*/]|\\(?:cdot|times)(?:\s*)|\s+)+)(?=[。；，,.;!?！？]|$)/g,
      (_match, expression: string) => {
        const index = expressionParts.push(expression.trim()) - 1;
        return `\u0009${index}\u000A`;
      },
    )
    .replace(
      /(?<![$\\\w])([A-Za-z][A-Za-z0-9_]*\s*=\s*(?:softmax|sigmoid|relu|tanh)\s*\([^()\n]*\))/gi,
      (_match, expression: string) => {
        const index = expressionParts.push(expression.trim()) - 1;
        return `\u0009${index}\u000A`;
      },
    );
  const normalized = withExpressions
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
    /(?<![$])(\\(?:alpha|beta|gamma|theta|lambda|mu|sigma|in|notin|cdot|times|dots|sum|prod|sqrt|left|right|lfloor|rfloor)(?![A-Za-z])(?:[_^](?:\{[^{}\n]+\}|[A-Za-z0-9+-]))?(?:\s*(?:=|≈)\s*\d+(?:\.\d+)?)?)/g,
    (_match, command: string) => `$${command}$`,
  );
  const namedAtoms = withCommands
    // Fractions have two braced arguments and need to stay in one math span.
    .replace(
      /(?<![$])(\\frac\s*\{[^{}\n]+\}\s*\{[^{}\n]+\})/g,
      (_match, fraction: string) => `$${fraction}$`,
    )
    // Render named TeX atoms such as \mathbf{v}, \mathbb{R} and \mathbb R.
    .replace(
      /(?<![$])(\\(?:mathbb|mathbf|mathrm|mathcal|mathsf|text)\s*(?:\{[^{}\n]+\}|[A-Za-z])(?:[_^](?:\{[^{}\n]+\}|[A-Za-z0-9+-]))?)/g,
      (_match, atom: string) => `$${atom}$`,
    );
  const vectorParts: string[] = [];
  const vectorSafe = namedAtoms.replace(
    // Lock vector/list equalities before indexing symbols to avoid nested `$`.
    /(?<![$\w])(\[[^\]\n]+\]\s*=\s*\[[^\]\n]+\])(?!\w)/g,
    (_match, equation: string) => {
      const index = vectorParts.push(equation) - 1;
      return `\u0007${index}\u0008`;
    },
  );
  const withAtoms = vectorSafe
    // Render indexed symbols that are commonly emitted outside delimiters.
    .replace(
      /(?<![$\\\w])([A-Za-z](?:[_^](?:\{[^{}\n]+\}|[A-Za-z0-9+-]))+)(?!\w)/g,
      (_match, atom: string) => `$${atom}$`,
    );
  return withAtoms
    .replace(/\u0003(\d+)\u0004/g, (_match, index: string) => formulaParts[Number(index)])
    .replace(/\u0001(\d+)\u0002/g, (_match, index: string) => protectedParts[Number(index)])
    .replace(
      /\u0005(\d+)\u0006/g,
      (_match, index: string) => promoteComplex
        ? `$$\n${environments[Number(index)]}\n$$`
        : inlineEnvironmentText(environments[Number(index)]),
    )
    .replace(/\u0009(\d+)\u000A/g, (_match, index: string) => `$${expressionParts[Number(index)]}$`)
    .replace(/\u0007(\d+)\u0008/g, (_match, index: string) => `$${vectorParts[Number(index)]}$`);
}

function inlineEnvironmentText(source: string): string {
  const isMatrix = source.includes("&");
  const body = source.replace(/\\begin\{[^{}\n]+\}|\\end\{[^{}\n]+\}/g, "").replace(/\\[,;! ]/g, " ").trim();
  const rows = body.split("\\\\").map((row) => row.replace(/\s*&\s*/g, ", ").trim()).filter(Boolean);
  return "[" + rows.join(isMatrix ? "; " : ", ") + "]";
}

function flattenInlineMath(source: string): string {
  const body = source.replace(/^\$+|\$+$/g, "");
  return body.replace(
    /\\begin\{[^{}\n]+\}[\s\S]*?\\end\{[^{}\n]+\}/g,
    (environment) => inlineEnvironmentText(environment),
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
  // Keep question formulas in one inline line box. Display delimiters from a
  // generated question otherwise create a tall block inside the option row.
  const source = String(value);
  // Generated options often contain a complete TeX expression without dollar
  // delimiters (for example `\\sum_{k=1}^n A_{ik}B_{kj}`). If we normalize
  // that text atom by atom, KaTeX receives three independent spans and their
  // baselines no longer line up. Standalone TeX-like options can be protected
  // as one expression before the generic bare-command recovery runs.
  const trimmed = source.trim();
  const standaloneTex = !trimmed.includes("$")
    && !/[\u3400-\u9fff]/.test(trimmed)
    && /\\(?:sum|prod|frac|sqrt|begin|left|right|times|cdot|in|notin)(?![A-Za-z])/.test(trimmed)
    && /^[\\A-Za-z0-9\s_{}^=+*/().,\-\[\]|]+$/.test(trimmed);
  const normalized = normalizeMath(standaloneTex ? `$${trimmed}$` : source, false).replace(
    /\$\$([\s\S]*?)\$\$/g,
    (_match, body: string) => `$${body.replace(/\s+/g, " ").trim()}$`,
  );
  return markdown.renderInline(normalized);
}
