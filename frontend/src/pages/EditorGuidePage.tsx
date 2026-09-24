import { useEffect } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";

import editorialGuide from "../content/editorial-guide.md?raw";
import "./editor-guide.css";

export function EditorialMarkdown({ children }: { children: string }) {
  return (
    <div className="editorial-markdown">
      <Markdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSlug, { prefix: "guide-" }]]}
        components={{
          h1: ({ id, children }) => <h2 id={id}>{children}</h2>,
          h2: ({ id, children }) => <h3 id={id}>{children}</h3>,
          h3: ({ id, children }) => <h4 id={id}>{children}</h4>,
          a: ({ href, children }) => (
            <a href={href} target={/^(https?:)?\/\//.test(href ?? "") ? "_blank" : undefined} rel="noopener noreferrer">{children}</a>
          ),
          table: ({ children }) => <div className="editorial-markdown__table" tabIndex={0} role="group" aria-label="Таблица руководства"><table>{children}</table></div>,
        }}
      >{children}</Markdown>
    </div>
  );
}

export function EditorGuidePage() {
  useEffect(() => {
    try {
      const id = decodeURIComponent(window.location.hash.slice(1));
      if (id.startsWith("guide-")) document.getElementById(id)?.scrollIntoView();
    } catch { /* Ignore malformed URL fragments without changing the guide. */ }
  }, []);
  return (
    <article className="editor-guide">
      <header><p className="eyebrow">Помощь редактору</p><h1>Правила заполнения карточек</h1></header>
      <EditorialMarkdown>{editorialGuide}</EditorialMarkdown>
    </article>
  );
}
