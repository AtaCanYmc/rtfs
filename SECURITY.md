# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :--- |
| `0.1.x` | Yes |
| `< 0.1.0` | No |

## Reporting a Vulnerability

Do not open public GitHub issues for security vulnerabilities.

Report suspected vulnerabilities privately via GitHub Security Advisories at:
`https://github.com/AtaCanYmc/rtfs/security/advisories/new`

Include the following details in your report:

1. Affected module and version (`src/rtfs/...`).
2. Minimal reproduction payload (malformed PDF, HTML snippet, or URL response).
3. Impact assessment (arbitrary file write, SSRF, parser denial of service).

## Response Timeline

- **Acknowledgment**: Within 48 hours of submission.
- **Triage & Reproduction**: Within 5 business days.
- **Patch & Advisory Publication**: Within 14 days of confirmed reproduction.

## Scope Considerations

`rtfs` parses untrusted external HTML (`selectolax` Lexbor backend) and PDF binaries (`pymupdf`). Reports demonstrating memory corruption, infinite loops during coordinate clustering, path traversal in `--output`, or cache poisoning in `ScriptCache` are in scope.
