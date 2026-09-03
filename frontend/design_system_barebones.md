# Barebones Pragmatic Web — Design System

## Brand & Style
This design system is engineered for utilitarian web applications rendered cleanly through standard server-side templating engines (such as Django, Rails, or Laravel). The aesthetic rejects excessive ornamentation, artificial 3D depth, aggressive floating cards, and superfluous dashboard widgets. Instead, it prioritizes content clarity, high data density, rapid scanability, and bulletproof browser defaults.

The design movement is **Minimalist / Utilitarian Modernism**. The visual language is disciplined, quiet, and structured:
- **Pragmatic over decorative:** Visual components earn their place strictly through functional utility. White space is functional padding rather than wasteful empty canvas.
- **Structured tabular layouts:** Information hierarchy is defined through structural hairline rules, aligned tabular columns, and strict typographical rhythm rather than nested container boxes.
- **Predictable affordances:** Links look like actionable links, inputs have crisp perimeter definition, and interactive elements provide instantaneous visual feedback without heavy animation libraries.
- **Fast and accessible:** Built to excel with system-level rendering speeds, clear semantic HTML structures, and accessible contrast ratios.

## Layout & Spacing
This design system uses a strict **fixed-container fluid layout** designed for native server templates. Instead of infinite multi-directional canvases or unpredictable fluid masonry, content sits within a centered container maxing out at `1120px` (or standard `100%` width with `16px` to `24px` gutter protection on smaller viewports).

### Layout Rules
- **Base Grid Unit:** All vertical rhythms, padding increments, and line gaps scale from a crisp 4px / 8px baseline.
- **Section Stack:** Pages follow a top-to-bottom vertical rhythm. Major functional areas (e.g., Connected Mailboxes vs. Incoming Emails) are separated by clear `32px` (`space-xl`) breaks paired with a single-pixel divider line (`border-top: 1px solid #e2e8f0`).
- **Two-Column Form Rhythm:** Settings and profile layouts use a standard two-column configuration on desktop (`>= 768px`): a 1/3 width column for section title and brief instructions, and a 2/3 width column containing the functional form elements.
- **Responsive Handling:**
  - **Desktop (`>= 1024px`):** Full tabular layouts with dedicated action columns and visible metadata fields.
  - **Tablet (`768px - 1023px`):** Preserves table layouts, truncating auxiliary non-essential columns (e.g., raw message IDs).
  - **Mobile (`< 768px`):** Side-by-side forms wrap to a single vertical column. Tables allow horizontal scrolling (`overflow-x: auto`) with sticky subject columns or convert cleanly into simple vertical stacked rows.

## Colors
The palette is tuned specifically for light mode, emphasizing neutral slate and zinc values that keep data readability front and center while eliminating eye strain.

- **Primary (`#2563eb`):** Direct action blue. Used exclusively for primary form submissions, active navigation indicators, key focus rings, and highlighted interactive links.
- **Secondary (`#475569`):** Slate gray. Employed for supporting metadata, table column headings, auxiliary badges, and de-emphasized actions.
- **Neutral Core (`#0f172a`):** Deep slate-black. Delivers maximum contrast for body text, primary data values, and titles without the harshness of pure black (`#000000`).
- **Surface & Backgrounds:** Pure white (`#ffffff`) serves as the base viewport canvas and input background. A faint tinted gray (`#f8fafc`) is reserved for table headers, active row hovers, code blocks, and subtle section zebra striping.
- **Border / Hairlines (`#e2e8f0`):** Defines table rows, field boundaries, and section dividers. High contrast alternative (`#cbd5e1`) is available for input borders to guarantee WCAG compliance.
- **Functional Semantics:**
  - **Success:** `#16a34a` (green text on `#f0fdf4` tint) for connected mailbox statuses and verified items.
  - **Warning / Pending:** `#d97706` (amber text on `#fffbeb` tint) for synchronization states.
  - **Critical / Danger:** `#dc2626` (red text on `#fef2f2` tint) for deletion, disconnect actions, or validation failures.

## Typography
- Typography uses **`Geist`** across all roles for tabular numeric alignment and compact vertical metric bounding boxes. `Inter` serves as system fallback.
- `headline-xl`: 28px / 36px, Weight 600, -0.02em
- `headline-lg`: 22px / 28px, Weight 600, -0.015em
- `headline-sm`: 16px / 24px, Weight 600, -0.01em
- `body-lg`: 15px / 22px, Weight 400, -0.005em
- `body-md`: 14px / 20px, Weight 400, 0em
- `body-sm`: 13px / 18px, Weight 400, 0em
- `label-md`: 13px / 16px, Weight 500, 0.01em
- `label-sm`: 11px / 14px, Weight 600, 0.04em
- `code-sm`: 12px / 16px, Weight 400, 0em
