# ADR 0004: Geometry must carry provenance

**Status:** Accepted (Phase 1)

**Context.** The specification forbids invented coordinates and administrative
relationships.

**Decision.** All geometry is EPSG:4326. Every table with geometry has a
`geometry_dataset_id` referencing `ref.boundary_datasets` (publisher, version,
source reference, checksum, verification), and a CHECK constraint makes it
mandatory whenever geometry is present. Geometries must be valid (`ST_IsValid`).
Hierarchy links that are not universally true (block → subdivision, village → GP)
are nullable and filled only from source data.

**Consequences.** Unverified geometry cannot be stored silently; every map layer can
show its source. Imports (Phase 6) must register the dataset first.
