"""Rule registry: every tax figure comes from here, with citation, effective range and test vectors."""

from .registry import Registry, Rule, RuleNotFound, RuleResult, load_rules, registry

__all__ = ["Registry", "Rule", "RuleNotFound", "RuleResult", "load_rules", "registry"]
