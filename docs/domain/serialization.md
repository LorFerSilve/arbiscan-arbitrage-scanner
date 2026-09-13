# Canonical serialization

ArbiScan provides a small internal JSON codec in `arbiscan.domain.serialization` for deterministic snapshots, fixtures, audit records, and persistence boundaries.

## Properties

- envelope contains `schema_version`;
- JSON output is deterministic (`sort_keys=True`, compact separators);
- `Decimal` values serialize as decimal strings, never binary floats;
- datetimes retain explicit offsets and canonical entities normalize them back to UTC;
- tuples retain tuple semantics through an explicit tag;
- enums retain their enum type and value;
- IDs and domain entities retain exact canonical types;
- decoder uses a closed registry and never dynamically imports a type named by input data;
- every serialized domain object must contain **exactly** the complete canonical field set for that schema version;
- omitted defaulted fields are rejected rather than silently reconstructed with current Python defaults;
- unexpected fields are rejected rather than ignored;
- tagged primitive objects and the top-level envelope also require their exact expected key sets;
- unknown type tags, enum values, schema versions, malformed payloads, and unexpected root types fail closed.

Example envelope shape:

```json
{
  "schema_version": 1,
  "payload": {
    "$type": "Event",
    "id": {"$type": "EventId", "value": "event:example"}
  }
}
```

This format is an **internal canonical snapshot format**, not the public HTTP API contract. A future external API may use a different representation while mapping losslessly to the same domain entities.

Schema-version changes must be explicit. Incompatible changes require a new schema version and migration/compatibility policy rather than silent reinterpretation. In particular, adding or removing canonical fields requires version-aware migration instead of relying on dataclass default values during deserialization.
