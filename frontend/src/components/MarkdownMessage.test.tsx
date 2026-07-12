import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarkdownMessage } from "./MarkdownMessage";

describe("MarkdownMessage", () => {
  it("renders inline mathematics while preserving surrounding text", () => {
    const { container } = render(
      <MarkdownMessage
        content={String.raw`For every $x \in X$, we have $Tx \in Y$.`}
      />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(screen.getByText(/For every/)).toBeInTheDocument();
    expect(container.textContent).not.toContain("$x \\in X$");
  });

  it("renders display mathematics in its own scrollable display container", () => {
    const { container } = render(
      <MarkdownMessage
        content={String.raw`$$
\|Tx\| \leq C\|x\|
$$`}
      />,
    );

    expect(container.querySelector(".katex-display > .katex")).not.toBeNull();
    expect(
      container.querySelector(".markdown-message .katex-display"),
    ).not.toBeNull();
  });

  it("combines GFM headings, lists, tables, citations, and mathematics", () => {
    const { container } = render(
      <MarkdownMessage
        content={String.raw`## Theorem

- Let $X$ be Banach.
- By [S1], let $Y$ be Banach.

| Symbol | Meaning |
| --- | --- |
| $T$ | Operator |

$$
T:X\to Y
$$`}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Theorem" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/\[S1\]/)).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(
      4,
    );
  });

  it("turns only S/W markers into safe citation buttons", () => {
    const activate = vi.fn();
    render(
      <MarkdownMessage
        content="Use [S1], [W2], and `[S3]`."
        onCitationActivate={activate}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Show source S1" }));
    fireEvent.click(screen.getByRole("button", { name: "Show source W2" }));
    expect(activate.mock.calls).toEqual([["S1"], ["W2"]]);
    expect(screen.getByText("[S3]", { selector: "code" })).toBeInTheDocument();
  });

  it("keeps dollar-delimited text inside inline and fenced code out of KaTeX", () => {
    const content = [
      "Inline: `$x$`",
      "",
      "```python",
      'price = "$10"',
      'value = "$x$"',
      "```",
    ].join("\n");
    const { container } = render(<MarkdownMessage content={content} />);

    expect(container.querySelector(".katex")).toBeNull();
    expect(screen.getByText("$x$", { selector: "code" })).toBeInTheDocument();
    expect(container.querySelector("pre")?.textContent).toContain(
      'value = "$x$"',
    );
  });

  it("does not crash for invalid math", () => {
    const { container } = render(
      <MarkdownMessage
        content={String.raw`$$
\frac{
$$`}
      />,
    );

    expect(container.querySelector(".katex-error")).not.toBeNull();
    expect(container.textContent).toContain("\\frac{");
  });

  it("does not turn raw HTML or unsafe links into executable content", () => {
    const { container } = render(
      <MarkdownMessage
        content={
          '<script>alert("xss")</script>\n\n[unsafe](javascript:alert(1))'
        }
      />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("a")).toHaveAttribute("href", "");
    expect(container).toHaveTextContent('<script>alert("xss")</script>');
  });

  it("adds safe attributes to external links", () => {
    render(<MarkdownMessage content="[OpenAI](https://openai.com)" />);

    expect(screen.getByRole("link", { name: "OpenAI" })).toHaveAttribute(
      "rel",
      "noreferrer noopener",
    );
    expect(screen.getByRole("link", { name: "OpenAI" })).toHaveAttribute(
      "target",
      "_blank",
    );
  });

  it("keeps a wide matrix inside the message display container", () => {
    const { container } = render(
      <MarkdownMessage
        content={String.raw`$$
\begin{bmatrix}
a_{11} & a_{12} & a_{13} & a_{14} & a_{15} & a_{16} \\
a_{21} & a_{22} & a_{23} & a_{24} & a_{25} & a_{26}
\end{bmatrix}
$$`}
      />,
    );

    const message = container.querySelector<HTMLElement>(".markdown-message");
    const display = container.querySelector<HTMLElement>(".katex-display");
    expect(message).toContainElement(display);
    expect(display?.querySelector(":scope > .katex")).not.toBeNull();
  });
});
