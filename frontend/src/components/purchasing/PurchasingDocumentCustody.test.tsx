import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { PurchasingDocumentCustody } from "./PurchasingDocumentCustody";

it("retains failed custody evidence, announces failure, and retries safely", async () => {
  const register = vi
    .fn()
    .mockRejectedValueOnce(new Error("protected backend detail"))
    .mockResolvedValueOnce({ id: "document-1" });
  render(
    <PurchasingDocumentCustody
      canManage
      documents={[]}
      register={register}
      pending={false}
      failed={false}
    />,
  );

  fireEvent.change(screen.getByLabelText("Document branch ID"), {
    target: { value: "branch-1" },
  });
  fireEvent.change(screen.getByLabelText("Document entity ID"), {
    target: { value: "entity-1" },
  });
  fireEvent.change(screen.getByLabelText("Document filename"), {
    target: { value: "invoice.pdf" },
  });
  fireEvent.change(screen.getByLabelText("Document SHA-256"), {
    target: { value: "a".repeat(64) },
  });
  fireEvent.change(screen.getByLabelText("Authorized storage reference"), {
    target: { value: "evidence://purchasing/invoice" },
  });
  fireEvent.change(screen.getByLabelText("Source reference"), {
    target: { value: "synthetic-qualification" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Register evidence" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "No custody authority was assumed",
  );
  expect(screen.getByLabelText("Document filename")).toHaveValue("invoice.pdf");
  expect(screen.queryByText("protected backend detail")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Retry registration" }));
  await waitFor(() => expect(register).toHaveBeenCalledTimes(2));
  await waitFor(() =>
    expect(screen.getByLabelText("Document filename")).toHaveValue(""),
  );
});
