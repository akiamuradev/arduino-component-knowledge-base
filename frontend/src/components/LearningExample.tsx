import { useState } from "react";

import type { CodeExample } from "../api/contracts";

const keywords = new Set([
  "break", "case", "class", "const", "continue", "def", "delay", "digitalRead",
  "digitalWrite", "else", "false", "float", "for", "HIGH", "if", "import", "include",
  "INPUT", "int", "LOW", "loop", "OUTPUT", "pinMode", "return", "setup", "String",
  "true", "void", "while",
]);

function tokenClass(token: string): string | undefined {
  if (token.startsWith("//") || token.startsWith("#")) return "code-token--comment";
  if (token.startsWith('"') || token.startsWith("'")) return "code-token--string";
  if (/^\d/.test(token)) return "code-token--number";
  if (keywords.has(token)) return "code-token--keyword";
  return undefined;
}

export function SyntaxHighlightedCode({ body, language }: { body: string; language: string }) {
  const tokens = body.split(/(\/\/[^\n]*|#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b)/g);
  return (
    <pre className="learning-code" data-language={language}>
      <code>{tokens.map((token, index) => <span className={tokenClass(token)} key={`${String(index)}:${token}`}>{token}</span>)}</code>
    </pre>
  );
}

export function LearningExample({ example }: { example: CodeExample }) {
  const [visibleHints, setVisibleHints] = useState(0);
  const [solutionVisible, setSolutionVisible] = useState(false);
  return (
    <article className="learning-example">
      <header>
        <div><p className="eyebrow">Практическое задание</p><h3>{example.title}</h3></div>
        <span className="status-badge">{example.language}</span>
      </header>
      <p className="preserve-lines">{example.practical_task}</p>
      {example.libraries.length > 0 ? <p><strong>Библиотеки:</strong> {example.libraries.join(", ")}</p> : null}
      {visibleHints > 0 ? (
        <ol className="learning-hints">
          {example.hints.slice(0, visibleHints).map((hint, index) => <li key={`${String(index)}:${hint}`}>{hint}</li>)}
        </ol>
      ) : null}
      {visibleHints < example.hints.length ? (
        <button className="button button--quiet" type="button" onClick={() => { setVisibleHints((current) => current + 1); }}>
          Показать подсказку {visibleHints + 1}
        </button>
      ) : null}
      {!solutionVisible ? (
        <button className="button button--primary" type="button" onClick={() => { setSolutionVisible(true); }}>Показать решение</button>
      ) : (
        <section><h4>Решение</h4><SyntaxHighlightedCode body={example.body} language={example.language} />
          {example.explanation ? <p className="preserve-lines">{example.explanation}</p> : null}
        </section>
      )}
    </article>
  );
}
