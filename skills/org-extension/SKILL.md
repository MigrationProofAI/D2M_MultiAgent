---
name: org-extension
description: How to extend an existing material to a new plant or organizational level without creating new materials or altering basic data.
when_to_trigger: When a request asks to extend, add, or set up an existing material (or its components) for a new plant, MRP area, valuation area, sales org, or other org level - as opposed to creating a new material.
verification: Confirm the proposed action adds only org-level views and does not create any new material number or modify basic-data fields (material group, material type, base unit, description).
---

## Org-level extension, not creation

When asked to extend an existing material to a new plant or organizational level:

- Add **only** the requested org views (e.g. plant / MRP / valuation / sales). Do not touch anything else.
- **Never create a new material.** The material already exists; this is an extension of an existing material number, not a new genesis.
- **Never change basic data** - material group, material type, base unit of measure, description. These were set at creation and are out of scope. If they look "wrong," that is not the task; the task is the org-level extension only.
- Ground the org-view values (valuation class, procurement type, MRP type, etc.) from the codebook for that plant - do not invent or default them.
- Preview the exact payload (which views, which fields, which values) and wait for explicit confirmation before writing.

