import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import AdminLayout from "@/features/admin/AdminLayout";

describe("AdminLayout", () => {
  it("renders the Qdrant navigation item and nested route content", () => {
    render(
      <MemoryRouter initialEntries={["/admin/qdrant"]}>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="qdrant" element={<div>Qdrant diagnostics page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Qdrant и RAG" })).toHaveAttribute(
      "href",
      "/admin/qdrant",
    );
    expect(screen.getByText("Qdrant diagnostics page")).toBeInTheDocument();
  });
});
