# Security policy

Joinery runs SQL submitted by anyone who can reach it, so sandbox escapes and denial-of-service problems are taken seriously.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **Report a vulnerability** button on the repository's Security tab, rather than in a public issue. Include the SQL or request that demonstrates the problem, the engine and versions involved, and the impact you observed. You should receive an acknowledgement within a week.

## In scope

- Escaping the sandbox: reading or writing files, running programs, reaching the network, or seeing the server's environment from SQL
- Exhausting resources despite the limits described in [docs/security.md](docs/security.md)
- Making permanent changes to the shared databases of server engines
- Script injection or Content Security Policy bypasses in the client

## Supported versions

Only the latest release on the `main` branch receives security fixes.
