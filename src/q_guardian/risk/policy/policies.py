"""Built-in policy definitions.

Provides factory methods for creating common security policies.
"""

from __future__ import annotations

from q_guardian.risk.data import PolicyDefinition, PolicyRule
from q_guardian.risk.enums import PolicyAction, PolicySeverity


def create_default_policy() -> PolicyDefinition:
    """Create the default security policy.

    Maps risk levels to standard security actions:
    - MINIMAL/LOW -> ALLOW
    - MODERATE -> WARN + LOG
    - HIGH -> REVIEW + LOG
    - SEVERE/CRITICAL -> BLOCK + ESCALATE
    """
    return PolicyDefinition(
        name="default-security",
        description="Default security policy for Q-Guardian",
        rules=[
            PolicyRule(
                condition="risk_level == 'critical'",
                action=PolicyAction.BLOCK,
                severity=PolicySeverity.CRITICAL,
                description="Block critical threats immediately",
                priority=0,
            ),
            PolicyRule(
                condition="risk_level == 'severe'",
                action=PolicyAction.ESCALATE,
                severity=PolicySeverity.HIGH,
                description="Escalate severe threats for review",
                priority=10,
            ),
            PolicyRule(
                condition="risk_level == 'high'",
                action=PolicyAction.REVIEW,
                severity=PolicySeverity.HIGH,
                description="Queue high-risk threats for review",
                priority=20,
            ),
            PolicyRule(
                condition="risk_level == 'moderate'",
                action=PolicyAction.WARN,
                severity=PolicySeverity.MEDIUM,
                description="Warn on moderate threats",
                priority=30,
            ),
            PolicyRule(
                condition="risk_level == 'low'",
                action=PolicyAction.LOG,
                severity=PolicySeverity.LOW,
                description="Log low-risk threats",
                priority=40,
            ),
        ],
        default_action=PolicyAction.ALLOW,
        tags=["default", "security"],
    )


def create_strict_policy() -> PolicyDefinition:
    """Create a strict security policy.

    More aggressive than default — blocks at HIGH and above.
    """
    return PolicyDefinition(
        name="strict-security",
        description="Strict security policy — blocks high-risk threats",
        rules=[
            PolicyRule(
                condition="risk_level in ['critical', 'severe']",
                action=PolicyAction.BLOCK,
                severity=PolicySeverity.CRITICAL,
                description="Block severe/critical threats",
                priority=0,
            ),
            PolicyRule(
                condition="risk_level == 'high'",
                action=PolicyAction.BLOCK,
                severity=PolicySeverity.HIGH,
                description="Block high-risk threats",
                priority=10,
            ),
            PolicyRule(
                condition="risk_level == 'moderate'",
                action=PolicyAction.REVIEW,
                severity=PolicySeverity.MEDIUM,
                description="Review moderate threats",
                priority=20,
            ),
            PolicyRule(
                condition="risk_level == 'low'",
                action=PolicyAction.WARN,
                severity=PolicySeverity.LOW,
                description="Warn on low-risk threats",
                priority=30,
            ),
        ],
        default_action=PolicyAction.WARN,
        tags=["strict", "security"],
    )


def create_permissive_policy() -> PolicyDefinition:
    """Create a permissive policy.

    Only blocks critical threats, logs everything else.
    """
    return PolicyDefinition(
        name="permissive-security",
        description="Permissive policy — only blocks critical threats",
        rules=[
            PolicyRule(
                condition="risk_level == 'critical'",
                action=PolicyAction.BLOCK,
                severity=PolicySeverity.CRITICAL,
                description="Block critical threats only",
                priority=0,
            ),
            PolicyRule(
                condition="risk_level in ['severe', 'high']",
                action=PolicyAction.LOG,
                severity=PolicySeverity.MEDIUM,
                description="Log high-severe threats",
                priority=10,
            ),
        ],
        default_action=PolicyAction.ALLOW,
        tags=["permissive", "security"],
    )


def create_quarantine_policy() -> PolicyDefinition:
    """Create a quarantine-focused policy.

    Quarantines high-risk threats instead of blocking.
    """
    return PolicyDefinition(
        name="quarantine-security",
        description="Quarantine-focused policy for research environments",
        rules=[
            PolicyRule(
                condition="risk_level in ['critical', 'severe']",
                action=PolicyAction.QUARANTINE,
                severity=PolicySeverity.HIGH,
                description="Quarantine severe/critical threats",
                priority=0,
            ),
            PolicyRule(
                condition="risk_level == 'high'",
                action=PolicyAction.REVIEW,
                severity=PolicySeverity.MEDIUM,
                description="Review high-risk threats",
                priority=10,
            ),
        ],
        default_action=PolicyAction.ALLOW,
        tags=["quarantine", "research"],
    )
