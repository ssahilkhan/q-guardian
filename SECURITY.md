# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability within Q-Guardian, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email the maintainers directly with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix or mitigation:** Depends on severity

## Scope

This security policy applies to:

- The Q-Guardian framework source code
- The plugin architecture and extension points
- The quantum computing layer

## Out of Scope

- Third-party dependencies (report upstream)
- Deployments and infrastructure configurations
- Social engineering attacks

## Security Best Practices

When deploying Q-Guardian:

- Use environment variables for secrets (never commit them)
- Enable CORS restrictions for production deployments
- Use HTTPS in production
- Keep dependencies updated
- Run the framework with least-privilege permissions

## Contact

For security inquiries, contact the Q-Guardian Research Team.
