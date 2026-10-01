"""One deny policy for Logins allowlisting, proxying, and Hermes."""

DENY_TERMS = (
    "bank", "credit", "payment", "payroll", "mail", "inbox",
    "stripe", "paypal", "chase", "wellsfargo", "gusto", "adp",
    "outlook", "paychex",
)

DENY_DOMAINS = (
    "paypal.com", "stripe.com", "chase.com", "bankofamerica.com",
    "wellsfargo.com", "gmail.com", "outlook.com", "mail.google.com",
    "adp.com", "gusto.com", "paychex.com",
)


def denied(domain: str) -> bool:
    return any(term in domain for term in DENY_TERMS) or any(
        domain == base or domain.endswith("." + base) for base in DENY_DOMAINS
    )


def hermes_blocklist() -> list[str]:
    return [pattern for domain in DENY_DOMAINS for pattern in (domain, "*." + domain)]
