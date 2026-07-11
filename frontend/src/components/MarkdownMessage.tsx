import { Component, ErrorInfo, ReactNode, memo } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

interface MarkdownMessageProps {
  content: string;
}

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

function MarkdownMessageView({ content }: MarkdownMessageProps) {
  return (
    <MarkdownMessageErrorBoundary content={content}>
      <div className="answer-text markdown-message">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[
            [
              rehypeKatex,
              { strict: "warn", trust: false, throwOnError: false },
            ],
          ]}
          components={{
            a: ({ children, ...props }) => (
              <a {...props} rel="noreferrer noopener" target="_blank">
                {children}
              </a>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </MarkdownMessageErrorBoundary>
  );
}

export const MarkdownMessage = memo(MarkdownMessageView);
