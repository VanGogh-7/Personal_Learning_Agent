import { Component, ComponentProps, ErrorInfo, ReactNode, memo } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

interface MarkdownMessageProps {
  content: string;
  onCitationActivate?: (citationId: string) => void;
}

const REMARK_PLUGINS: ComponentProps<typeof ReactMarkdown>["remarkPlugins"] = [
  remarkGfm,
  remarkMath,
  citationLinksPlugin,
];
const REHYPE_PLUGINS: ComponentProps<typeof ReactMarkdown>["rehypePlugins"] = [
  [rehypeKatex, { strict: "warn", trust: false, throwOnError: false }],
];

class MarkdownMessageErrorBoundary extends Component<
  { children: ReactNode; content: string },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("Agent message rendering failed", error, info);
    }
  }

  componentDidUpdate(previousProps: Readonly<{ content: string }>) {
    if (this.state.failed && previousProps.content !== this.props.content) {
      this.setState({ failed: false });
    }
  }

  render() {
    if (this.state.failed) {
      return <div className="markdown-fallback">{this.props.content}</div>;
    }
    return this.props.children;
  }
}

function MarkdownMessageView({
  content,
  onCitationActivate,
}: MarkdownMessageProps) {
  const components: ComponentProps<typeof ReactMarkdown>["components"] = {
    a: ({ children, href, ...props }) => {
      const citationId = citationIdFromHref(href);
      if (citationId) {
        return (
          <button
            type="button"
            className="citation-marker"
            aria-label={`Show source ${citationId}`}
            onClick={() => onCitationActivate?.(citationId)}
          >
            {children}
          </button>
        );
      }
      return (
        <a {...props} href={href} rel="noreferrer noopener" target="_blank">
          {children}
        </a>
      );
    },
  };
  return (
    <MarkdownMessageErrorBoundary content={content}>
      <div className="answer-text markdown-message">
        <ReactMarkdown
          remarkPlugins={REMARK_PLUGINS}
          rehypePlugins={REHYPE_PLUGINS}
          components={components}
        >
          {content}
        </ReactMarkdown>
      </div>
    </MarkdownMessageErrorBoundary>
  );
}

export const MarkdownMessage = memo(MarkdownMessageView);

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
}

export function citationLinksPlugin() {
  return (tree: MarkdownNode) => transformCitationText(tree);
}

function transformCitationText(node: MarkdownNode): void {
  if (
    !node.children ||
    ["link", "code", "inlineCode", "math", "inlineMath"].includes(node.type)
  ) {
    return;
  }
  node.children = node.children.flatMap((child) => {
    if (child.type !== "text" || !child.value) {
      transformCitationText(child);
      return [child];
    }
    const parts: MarkdownNode[] = [];
    const pattern = /\[((?:S|W)\d+)\]/g;
    let start = 0;
    for (const match of child.value.matchAll(pattern)) {
      const index = match.index ?? 0;
      if (index > start) {
        parts.push({ type: "text", value: child.value.slice(start, index) });
      }
      parts.push({
        type: "link",
        url: `#citation-${match[1]}`,
        children: [{ type: "text", value: match[0] }],
      });
      start = index + match[0].length;
    }
    if (start === 0) return [child];
    if (start < child.value.length) {
      parts.push({ type: "text", value: child.value.slice(start) });
    }
    return parts;
  });
}

function citationIdFromHref(href?: string): string | null {
  const match = href?.match(/^#citation-((?:S|W)\d+)$/);
  return match?.[1] || null;
}
