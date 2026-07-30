from agent_platform.domain import ApiError, ErrorCode, Role, TenantContext


def test_roles_from_prd() -> None:
    assert Role.ADMIN == "R-ADMIN"
    assert set(Role) == {Role.ADMIN, Role.DEV, Role.OPS, Role.AUDIT}


def test_api_error_payload() -> None:
    err = ApiError(ErrorCode.AGENT_NAME_DUPLICATE, "name taken", {"name": "bot"})
    assert err.to_dict()["code"] == "AGENT_NAME_DUPLICATE"
    assert err.to_dict()["details"]["name"] == "bot"


def test_tenant_context_requires_ids() -> None:
    ctx = TenantContext(tenant_id="t1", actor_id="u1", roles=(Role.DEV,))
    assert ctx.has_role(Role.DEV)
    assert not ctx.has_role(Role.ADMIN)
