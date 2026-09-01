# Security

Please report vulnerabilities privately to the repository owner before opening a public issue.

The runtime avoids shell invocation and rejects lookup records containing newlines, carriage returns, or NUL bytes. API deployments should still use normal reverse-proxy limits, authentication where appropriate, and filesystem permissions that keep FST and dictionary paths read-only. Do not expose arbitrary model paths through an untrusted request.
