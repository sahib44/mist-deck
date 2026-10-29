import { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ImportSteps, validateMapping, MergeFields } from "./Imports";
import { RecipientPreview } from "./Campaigns";
import { ReplyComposer, TicketComposerState } from "./Tickets";
import { can, User } from "./api";
import { RecipientChips } from "./Recipients";
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
    function ComposerHarness() {
      const [draft, setDraft] = useState<TicketComposerState>({ mode: "messages", reply: "", note: "", resolution_note: "", target_status: "" });
      return <ReplyComposer draft={draft} onChange={setDraft} changingStatus={false} onSend={() => send(draft.mode, draft.mode === "messages" ? draft.reply : draft.note)} pending={false} error={null} />;
    }
    render(<ComposerHarness />);
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
  it("does not grant a retired support role access", () => {
    const user = { role: "support_staff", permissions: [] } as unknown as User;
    expect(can(user, "imports")).toBe(false);
    expect(can(user, "approve")).toBe(false);
    expect(can(user, "tickets")).toBe(false);
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


describe("team permissions and recipients", () => {
  it("grants everyday tools to heads and deletion only to the chair or director", () => {
    const member = { role: "competitions_member", permissions: [] } as unknown as User;
    expect(can(member, "campaigns")).toBe(true);
    expect(can(member, "approve")).toBe(true);
    expect(can(member, "delete")).toBe(false);
    expect(can({ ...member, role: "competitions_chair" }, "delete")).toBe(true);
    expect(can({ ...member, role: "director" }, "delete")).toBe(true);
    expect(can({ ...member, role: "technology_administrator" }, "delete")).toBe(false);
  });
  it("shows each recipient name and removes only the selected person", () => {
    const change = vi.fn();
    const recipients = [{ key: "one", name: "First Judge", email: "first@example.org" }, { key: "two", name: "Second Judge", email: "second@example.org" }];
    render(<RecipientChips recipients={recipients} onChange={change} />);
    expect(screen.getByText("First Judge")).toBeVisible();
    expect(screen.getByText("Second Judge")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Remove First Judge" }));
    expect(change).toHaveBeenCalledWith([recipients[1]]);
  });
});


describe("ticket status requirements", () => {
  it("marks a waiting-on-requester reply required and blocks sending without approval", () => {
    const state: TicketComposerState = { mode: "messages", reply: "Please provide more information.", note: "", resolution_note: "", target_status: "waiting_on_requester" };
    const view = render(<ReplyComposer draft={state} onChange={vi.fn()} changingStatus pending={false} error={null} needsApproval approved={false} onSend={vi.fn()} onRequestApproval={vi.fn()} />);
    expect(screen.getByLabelText("Public reply body")).toBeRequired();
    expect(screen.getByRole("button", { name: "Update status and send reply" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Request chair approval" })).toBeEnabled();
    view.rerender(<ReplyComposer draft={state} onChange={vi.fn()} changingStatus pending={false} error={null} needsApproval approved onSend={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Update status and send reply" })).toBeEnabled();
  });
  it("requires a private resolution note and keeps the requester reply optional", () => {
    render(<ReplyComposer draft={{ mode: "messages", reply: "", note: "", resolution_note: "Solved with the rules team.", target_status: "resolved" }} onChange={vi.fn()} changingStatus pending={false} error={null} onSend={vi.fn()} />);
    expect(screen.getByLabelText("Resolution note")).toBeRequired();
    expect(screen.getByLabelText("Public reply body")).not.toBeRequired();
  });
});
