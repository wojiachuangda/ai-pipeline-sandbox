"""Sandbox application package."""

from .alerting import (
    AlertRule,
    clear_rules,
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    update_rule,
)
from .audit import (
    AuditEntry,
    append_audit,
    clear_audit,
    query_audit,
)
from .compliance import (
    CompliancePolicy,
    clear_policies as clear_compliance_policies,
    delete_policy,
    get_policy,
    list_policies,
    set_policy,
)
from .core import health, ping
from .logging import (
    LogEntry,
    Span,
    TraceTree,
    clear_logs,
    clear_traces,
    get_spans,
    get_trace_tree,
    put_span,
    query_logs,
    write_log,
)
from .masking import mask_dict, mask_sensitive, mask_value
from .monitoring import (
    get_counters,
    get_global_status,
    increment_counter,
    reset_counters,
)
from .rbac import (
    Policy,
    add_policy,
    check_permission,
    clear_policies as clear_rbac_policies,
    remove_policy,
)

__all__ = [
    # core
    "health",
    "ping",
    # logging (AC-1, AC-2)
    "LogEntry",
    "Span",
    "TraceTree",
    "write_log",
    "query_logs",
    "clear_logs",
    "put_span",
    "get_spans",
    "get_trace_tree",
    "clear_traces",
    # alerting (AC-3)
    "AlertRule",
    "create_rule",
    "get_rule",
    "list_rules",
    "update_rule",
    "delete_rule",
    "clear_rules",
    # monitoring (AC-4)
    "get_global_status",
    "increment_counter",
    "get_counters",
    "reset_counters",
    # audit (AC-5)
    "AuditEntry",
    "append_audit",
    "query_audit",
    "clear_audit",
    # compliance (AC-6)
    "CompliancePolicy",
    "set_policy",
    "get_policy",
    "list_policies",
    "delete_policy",
    "clear_compliance_policies",
    # rbac (AC-7)
    "Policy",
    "add_policy",
    "check_permission",
    "remove_policy",
    "clear_rbac_policies",
    # masking (AC-8)
    "mask_value",
    "mask_dict",
    "mask_sensitive",
]
