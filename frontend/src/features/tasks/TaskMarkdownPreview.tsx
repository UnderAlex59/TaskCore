import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  markdown: string;
}

const markdownComponents: Components = {
  a({ children, href, title }) {
    return (
      <a
        className="font-medium text-[#0c66e4] underline-offset-4 hover:underline"
        href={href}
        rel="noreferrer"
        target="_blank"
        title={title}
      >
        {children}
      </a>
    );
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-4 border-[rgba(12,102,228,0.28)] bg-[#f7f8fa] px-4 py-3 text-[#44546f]">
        {children}
      </blockquote>
    );
  },
  code({ children }) {
    return (
      <code className="rounded-[6px] bg-[#f1f2f4] px-1.5 py-0.5 font-mono text-[0.92em] text-[#172b4d]">
        {children}
      </code>
    );
  },
  h1({ children }) {
    return (
      <h1 className="text-2xl font-semibold leading-tight text-[#172b4d]">
        {children}
      </h1>
    );
  },
  h2({ children }) {
    return (
      <h2 className="text-xl font-semibold leading-tight text-[#172b4d]">
        {children}
      </h2>
    );
  },
  h3({ children }) {
    return (
      <h3 className="text-lg font-semibold leading-tight text-[#172b4d]">
        {children}
      </h3>
    );
  },
  li({ children }) {
    return (
      <li className="pl-1">
        {children}
      </li>
    );
  },
  ol({ children }) {
    return (
      <ol className="list-decimal space-y-2 pl-6">
        {children}
      </ol>
    );
  },
  p({ children }) {
    return (
      <p className="leading-7">
        {children}
      </p>
    );
  },
  pre({ children }) {
    return (
      <pre className="overflow-x-auto rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#f7f8fa] p-4 font-mono text-sm leading-6">
        {children}
      </pre>
    );
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto rounded-[12px] border border-[rgba(9,30,66,0.12)]">
        <table className="min-w-full border-collapse text-left text-sm">
          {children}
        </table>
      </div>
    );
  },
  tbody({ children }) {
    return <tbody>{children}</tbody>;
  },
  td({ children }) {
    return (
      <td className="border-t border-[rgba(9,30,66,0.1)] px-4 py-3 align-top leading-6 text-[#172b4d]">
        {children}
      </td>
    );
  },
  th({ children }) {
    return (
      <th className="border-b border-[rgba(9,30,66,0.14)] bg-[#f7f8fa] px-4 py-3 align-top text-xs font-semibold uppercase text-[#44546f]">
        {children}
      </th>
    );
  },
  thead({ children }) {
    return <thead>{children}</thead>;
  },
  tr({ children }) {
    return <tr>{children}</tr>;
  },
  ul({ children }) {
    return (
      <ul className="list-disc space-y-2 pl-6">
        {children}
      </ul>
    );
  },
};

export default function TaskMarkdownPreview({ markdown }: Props) {
  const normalizedMarkdown = markdown.trim();

  if (!normalizedMarkdown) {
    return (
      <div className="min-h-[34rem] rounded-[16px] border border-dashed border-[rgba(9,30,66,0.16)] bg-[#fafbfc] px-5 py-8 text-sm leading-7 text-[#626f86]">
        Нет текста для предпросмотра.
      </div>
    );
  }

  return (
    <div className="text-anywhere min-h-[34rem] rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-4 text-[15px] leading-7 text-[#172b4d]">
      <div className="space-y-5">
        <ReactMarkdown
          components={markdownComponents}
          remarkPlugins={[remarkGfm]}
          skipHtml
        >
          {normalizedMarkdown}
        </ReactMarkdown>
      </div>
    </div>
  );
}
