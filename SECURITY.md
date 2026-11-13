# Security

Jev evaluates **untrusted data** from agent runs. It must not be used as the only authorization boundary for sensitive actions. See docs/architecture.md for the threat model.

Do not publish private traces or credentials in public issues. For a potential security issue, contact the repository maintainer privately through their public GitHub profile rather than posting exploit details. The project is an early developer release and does not promise a response SLA.

The policy `approved` field must come from a trusted human-approval channel; allowing an LLM to set it defeats the approval policy.
