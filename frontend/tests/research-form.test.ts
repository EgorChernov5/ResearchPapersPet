import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { ResearchForm } from "../src/components/ResearchForm/ResearchForm";
import { DEFAULT_RESEARCH_CONFIG } from "../src/constants";

describe("ResearchForm phase two configuration", () => {
  it("renders bounded inputs and an unchecked manual upload default", () => {
    const markup = renderToStaticMarkup(
      createElement(ResearchForm, {
        disabled: false,
        statusMessage: null,
        onSubmit: vi.fn(),
      }),
    );

    expect(markup).toContain('name="max_depth"');
    expect(markup).toContain('min="1" max="5"');
    expect(markup).toContain(`value="${DEFAULT_RESEARCH_CONFIG.pdf_top_n}"`);
    expect(markup).toContain('name="allow_manual_pdf_upload"');
    expect(markup).not.toContain('name="allow_manual_pdf_upload" checked=""');
  });
});
