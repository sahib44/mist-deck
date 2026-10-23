import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ImportSteps, validateMapping, MergeFields } from "./Imports";
import { RecipientPreview } from "./Campaigns";
import { ReplyComposer } from "./Tickets";
import { can, User } from "./api";
import { Loading, ErrorBox } from "./ui";

describe("import wizard", () => {
  it("shows current navigation and completed steps", () => {
    const view = render(<ImportSteps step={2} />);
    expect(screen.getByText("Map columns")).toHaveClass("current");
    view.rerender(<ImportSteps step={3} />);
    expect(screen.getByText("Map columns")).toHaveClass("complete");
    expect(screen.getByText("Analyze & review")).toHaveClass("current");
  });
  it("requires identity mapping and prevents duplicate column mappings", () => {
    expect(validateMapping({ notes: "Note" })).toContain("name or email");
    expect(
      validateMapping({ display_name: "Name", first_name: "Name" }),
    ).toContain("only be mapped once");
    expect(
      validateMapping({ display_name: "Name", primary_email: "Email" }),
    ).toBe("");
  });
  it("lets organizers select each surviving field", () => {
    const change = vi.fn();
    render(
      <MergeFields
        existing={{ organization: "Old Studio" }}
        incoming={{ organization: "New Studio" }}
        decisions={{}}
        onChange={change}
      />,
    );
    expect(screen.getByText("Old Studio")).toBeVisible();
    expect(screen.getByText("New Studio")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Keep Organization"), {
      target: { value: "incoming" },
    });
    expect(change).toHaveBeenCalledWith({ organization: "incoming" });
  });
});
describe("campaign preview", () => {
  it("shows exactly one personalized recipient at a time", () => {
    render(
      <RecipientPreview
        recipients={[
          {
            id: "1",
            recipient_email: "one@example.com",
            rendered_subject: "First",
            rendered_body: "Hello One",
            status: "pending",
          },
          {
            id: "2",
            recipient_email: "two@example.com",
            rendered_subject: "Second",
            rendered_body: "Hello Two",
            status: "pending",
          },
        ]}
      />,
    );
    expect(screen.getByText("Hello One")).toBeVisible();
    expect(screen.queryByText("Hello Two")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /two@example.com/ }));
    expect(screen.getByText("Hello Two")).toBeVisible();
    expect(screen.getByText("One recipient · No Cc or Bcc")).toBeVisible();
  });
});
describe("ticket composers", () => {
  it("keeps public and private text and send actions separate", async () => {
    const send = vi.fn().mockResolvedValue(undefined);
    render(<ReplyComposer onSend={send} pending={false} error={null} />);
    fireEvent.change(screen.getByLabelText("Public reply body"), {
      target: { value: "Public answer" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Internal note" }));
    expect(screen.getByLabelText("Private internal note")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Private internal note"), {
      target: { value: "Private context" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save private internal note" }),
    );
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("notes", "Private context"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Public reply" }));
    expect(screen.getByLabelText("Public reply body")).toHaveValue(
      "Public answer",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Send public sandbox reply" }),
    );
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("messages", "Public answer"),
    );
  });
});
describe("permissions and request feedback", () => {
  it("does not grant support import or campaign approval controls", () => {
    const user = { role: "support_staff", permissions: [] } as unknown as User;
    expect(can(user, "imports")).toBe(false);
    expect(can(user, "approve")).toBe(false);
    expect(can(user, "tickets")).toBe(true);
    expect(
      can(
        {
          ...user,
          role: "competitions_administrator",
          permissions: ["campaign_approver"],
        },
        "approve",
      ),
    ).toBe(true);
  });
  it("announces loading and persistent errors", () => {
    render(
      <>
        <Loading />
        <ErrorBox error={new Error("Mapping failed")} />
      </>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Loading records");
    expect(screen.getByRole("alert")).toHaveTextContent("Mapping failed");
  });
});
