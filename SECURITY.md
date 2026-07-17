# Security Policy

## Reporting a vulnerability

Report suspected vulnerabilities privately to the repository owner. Use a
private contact channel already available to you or exposed by the owner's
GitHub profile. If no private channel is available, contact the owner without
sensitive details and ask how to provide the report securely.

Do not open a public issue containing sensitive details, exploit instructions,
private documents, credentials, or a working attack against real data.

Include:

- the affected commit or package version and operating system;
- the relevant command and configuration;
- expected and observed behavior;
- the security impact and required preconditions;
- the smallest fictional reproducer that demonstrates the problem;
- any containment or mitigation already identified.

Remove secrets, personal information, private artifacts, and unrelated machine
details. There is no published response or remediation service-level agreement.

## Supported code

The project does not currently publish a formal supported-version matrix.
Security corrections are made on the current development line. This policy does
not assert that any package version has been published to an index.

## Security model

PAR is an offline renderer and verifier, not a sandbox. Runtime code makes no
network requests. It reads a caller-selected JSON job or output directory,
processes images and PDFs through third-party libraries, writes to a
caller-selected output directory, and may invoke a locally installed Poppler
`pdftoppm`.

Verifier references from the truth sidecar are restricted to path-safe basenames
whose resolved targets remain within the selected output directory. Absolute,
nested, drive-qualified, traversal, and symlink/reparse escape paths are
rejected. This confinement does not make malformed images, PDFs, or JSON safe to
parse.

Rendering overwrites generated filenames in the selected output directory,
retains unrelated or stale files, and is not an atomic directory transaction.
Failures can leave partial output. Use a new directory when old contents must not
be mixed with a new render.

The truth sidecar embeds the full job snapshot. Do not put credentials, secrets,
or sensitive source material in a job unless that information is intended to be
stored beside the output.

## Resource and parser risks

PAR currently has no upper bounds for JSON size, page/content counts, text
length, or output resolution. Image and PDF parsing runs in-process without
PAR-level CPU, memory, or time limits. If Poppler is available, the verifier
invokes it without a timeout; if it is absent, that optional check is reported as
skipped.

Treat untrusted jobs, truth sidecars, images, and PDFs as potentially hostile.
Use operating-system isolation and external resource limits, keep Python and
dependencies updated, and avoid running untrusted files with access to sensitive
directories or credentials.

PAR's metadata and fingerprint checks are narrow verification heuristics. They
are not malware scanning, anonymization, cryptographic signing, provenance
attestation, or proof that an artifact is genuine.
