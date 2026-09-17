# OddsPapi synthetic provider fixtures

These files are hand-authored, schema-faithful test data for Phase 16.4.

They are **not captured OddsPapi responses** and contain no live credentials, private
account metadata, or provider payload copied from an authenticated session. They exist
only to make parser, contract, and fail-closed behavior deterministic in ordinary CI.

The representative corpus covers:

- supported and unsupported sports;
- one football competition and pre-match fixture;
- the current football full-time 1X2 market plus an unsupported market family;
- bookmaker/market/selection activity and source timestamps;
- account request-limit metadata without account secrets;
- unknown-status and fixture-identity-drift negative cases.

Replace or augment these files with sanitized recorded fixtures only after the
repository has explicit permission to retain and redistribute such provider data.
