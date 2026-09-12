# Security Policy

## Reporting a vulnerability

Do not disclose exploitable vulnerabilities, leaked credentials, or provider secrets in a public issue. Use GitHub's private vulnerability reporting mechanism when available, or contact the repository owner privately.

## Secret handling

- Real secrets must never enter Git history.
- Local secrets belong in `.env` or another ignored runtime secret source.
- `.env.example` may contain variable names and non-sensitive examples only.
- CI credentials must use GitHub encrypted secrets or an equivalent protected secret store.
- Provider credentials must be scoped to the minimum permissions required.

## Credential compromise procedure

If a credential is exposed or suspected to be exposed:

1. revoke or rotate it at the provider immediately;
2. stop using the compromised value;
3. determine whether it reached Git history, logs, artifacts, caches, screenshots, or external services;
4. remove the exposed material where feasible, without treating history rewriting as a substitute for rotation;
5. review provider activity and account logs for misuse;
6. document the incident and prevention action without publishing the secret itself.

## Dependency policy

Third-party packages and GitHub Actions must be justified, actively maintained, license-compatible with the project's intended use, and pinned or locked where practical. See `docs/development/dependency-policy.md`.

## Supported versions

ArbiScan is pre-1.0. Security fixes target the current `main` branch until a release support policy is defined.
