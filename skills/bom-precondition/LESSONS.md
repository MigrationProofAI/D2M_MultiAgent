# Captured Lessons

## Lesson 1 — Plant-extend before BOM add
Source: session skateboard genesis (2026-06)
Fact: Every BOM component must be plant-extended to the target plant BEFORE you add it to the BOM. Adding first and extending later causes the BOM write to fail.

## Lesson 2 — HALB only with value-add sub-BOM
Source: session skateboard genesis (2026-06)
Fact: Do not create HALB materials for groupings that have no sub-assembly BOM or no value-add routing. If there is no value-add, use HAWA. Only promote to HALB when a real sub-assembly BOM + operations exist.

## Lesson 3 — Coded fields must be validated and returned
Source: session skateboard genesis (2026-06)
Fact: Coded fields (ProductGroup, MRPType, ValuationClass, etc.) must be validated from the live codebook before writing. These are getting missed — always call list_allowed_values or the plant config tools before setting any coded field.
