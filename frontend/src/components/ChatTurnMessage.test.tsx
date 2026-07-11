import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatTurnMessage } from "./ChatTurnMessage";

describe("ChatTurnMessage", () => {
  it("renders unfinished Markdown and LaTeX safely as streaming text", () => {
    const { container } = render(
      <ChatTurnMessage
        turn={{
          id: "pending",
          question: "Question",
          answer: "**unfinished $$\\frac{",
          status: "streaming",
          activity: {
            compact: true,
            steps: [
              {
                stage: "streaming",
                message: "正在生成回答",
                status: "active",
              },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText("**unfinished $$\\frac{")).toBeInTheDocument();
    expect(container.querySelector(".katex")).toBeNull();
  });

  it("uses the complete Markdown and KaTeX renderer only after completion", () => {
    const { container } = render(
      <ChatTurnMessage
        turn={{
          id: "complete",
          question: "Question",
          answer: "Inline $x^2$ and `price = '$5'`.",
          status: "completed",
        }}
      />,
    );
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(screen.getByText("price = '$5'")).toBeInTheDocument();
  });

  it("shows both real retrieval activities when both were emitted", () => {
    render(
      <ChatTurnMessage
        turn={{
          id: "both",
          question: "Question",
          answer: "",
          status: "pending",
          activity: {
            compact: false,
            steps: [
              {
                stage: "retrieving_local",
                message: "正在检索已选书籍",
                status: "active",
              },
              {
                stage: "searching_web",
                message: "正在搜索网络资料",
                status: "active",
              },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText("正在检索已选书籍")).toBeInTheDocument();
    expect(screen.getByText("正在搜索网络资料")).toBeInTheDocument();
  });
});
