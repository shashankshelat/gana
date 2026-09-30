import httpx
from app.connectors.base import BaseConnector, ConnectorMeta
from app.connectors.registry import register_connector


# Fields every Okta System Log event carries the same way
_OKTA_COMMON = {
    "metadata.uid": "uuid",
    "metadata.event_code": "eventType",
    "metadata.product.name": "$const:Okta",
    "metadata.product.vendor_name": "$const:Okta",
    "time": "published",
    "message": "displayMessage",
    "severity_id": {"path": "severity", "transform": "lower"},
    "status_id": {"path": "outcome.result", "transform": "lower"},
    "status_detail": "outcome.reason",
    "actor.user.uid": "actor.id",
    "actor.user.name": "actor.alternateId",
    "actor.user.full_name": "actor.displayName",
    "actor.user.type": "actor.type",
    "src_endpoint.ip": "client.ipAddress",
    "src_endpoint.location.city": "client.geographicalContext.city",
    "src_endpoint.location.country": "client.geographicalContext.country",
    "http_request.user_agent": "client.userAgent.rawUserAgent",
    "http_request.uid": "debugContext.debugData.requestId",
}

# The user the event is about: the target User where Okta names one
_OKTA_TARGET_USER = {
    "user.uid": "target[type=User].id",
    "user.name": "target[type=User].alternateId",
    "user.full_name": "target[type=User].displayName",
}


def _okta(activity_id: int, activity_name: str, extra: dict) -> dict:
    return {
        **_OKTA_COMMON,
        "activity_id": f"$const:{activity_id}",
        "activity_name": f"$const:{activity_name}",
        **extra,
    }


_AUTH = {
    # The authenticating user is the actor for sign-in events
    "user.uid": "actor.id",
    "user.name": "actor.alternateId",
    "user.full_name": "actor.displayName",
    "service.uid": "target[type=AppInstance].id",
    "service.name": "target[type=AppInstance].displayName",
    "session.uid": "authenticationContext.externalSessionId",
    "auth_protocol": "authenticationContext.authenticationProvider",
}
_ENTITY = {
    "entity.uid": "target[0].id",
    "entity.name": "target[0].displayName",
    "entity.type": "target[0].type",
}
_APP_RESOURCE = {
    "resource.uid": "target[type=AppInstance].id",
    "resource.name": "target[type=AppInstance].displayName",
    "resource.type": "$const:Application",
}
_GROUP = {
    "group.uid": "target[type=UserGroup].id",
    "group.name": "target[type=UserGroup].displayName",
}
# Admin/configuration event families (Entity Management); specific families above take precedence
_ADMIN_PREFIXES = [
    "application.", "policy.", "zone.", "directory.", "system.", "oauth2.", "app.oauth2.",
    "security.", "device.", "app.user_management.", "app.app_instance.", "org.",
]


def _route(name: str, when: dict, class_uid: int, mapping: dict) -> dict:
    return {"name": name, "when": {"field": "eventType", **when}, "class_uid": class_uid, "mapping": mapping}


# OCSF classes and activity ids verified against schema.ocsf.io: Authentication 3002, Account Change 3001,
# User Access Management 3005, Group Management 3006, Entity Management 3004, Base Event 0.
# Order matters: the first matching route wins.
OKTA_EVENT_ROUTES = [
    # ── Authentication (3002)
    _route("auth_logon", {"in": ["user.session.start", "user.authentication.sso", "user.session.access_admin_app"]},
           3002, _okta(1, "Logon", _AUTH)),
    _route("auth_logon_mfa", {"in": ["user.authentication.auth_via_mfa"]},
           3002, _okta(1, "Logon", {**_AUTH, "is_mfa": "$const:true"})),
    _route("auth_logoff", {"in": ["user.session.end", "user.session.clear"]}, 3002, _okta(2, "Logoff", _AUTH)),
    _route("auth_other", {"in": ["user.authentication.verify", "policy.evaluate_sign_on", "security.protected_action.attempt",
                                 "user.authentication.authenticate"]},
           3002, _okta(99, "Other", _AUTH)),
    _route("oauth_token", {"prefix": ["app.oauth2.token.grant", "app.oauth2.authorize", "app.oauth2.as.token.grant",
                                      "app.oauth2.as.authorize"]},
           3002, _okta(99, "Other", {**_AUTH, "user.uid": "target[type=User].id", "user.name": "target[type=User].alternateId"})),

    # ── Account Change (3001)
    _route("account_create", {"in": ["user.lifecycle.create"]}, 3001, _okta(1, "Create", _OKTA_TARGET_USER)),
    _route("account_enable", {"in": ["user.lifecycle.activate", "user.lifecycle.reactivate", "user.lifecycle.unsuspend"]},
           3001, _okta(2, "Enable", _OKTA_TARGET_USER)),
    _route("account_disable", {"in": ["user.lifecycle.deactivate", "user.lifecycle.suspend"]},
           3001, _okta(5, "Disable", _OKTA_TARGET_USER)),
    _route("account_delete", {"prefix": ["user.lifecycle.delete"]}, 3001, _okta(6, "Delete", _OKTA_TARGET_USER)),
    _route("password_change", {"in": ["user.account.update_password"]}, 3001, _okta(3, "Password Change", _OKTA_TARGET_USER)),
    _route("password_reset", {"in": ["user.account.reset_password", "user.lifecycle.password_reset"]},
           3001, _okta(4, "Password Reset", _OKTA_TARGET_USER)),
    _route("account_lock", {"in": ["user.account.lock", "user.account.lock.limit"]}, 3001, _okta(9, "Lock", _OKTA_TARGET_USER)),
    _route("account_unlock", {"prefix": ["user.account.unlock"]}, 3001, _okta(12, "Unlock", _OKTA_TARGET_USER)),
    _route("mfa_enable", {"in": ["user.mfa.factor.activate"]}, 3001, _okta(10, "MFA Factor Enable", _OKTA_TARGET_USER)),
    _route("mfa_disable", {"in": ["user.mfa.factor.deactivate", "user.mfa.factor.reset_all", "user.mfa.factor.suspend"]},
           3001, _okta(11, "MFA Factor Disable", _OKTA_TARGET_USER)),

    # ── User Access Management (3005)
    _route("privilege_grant", {"in": ["user.account.privilege.grant"]}, 3005, _okta(1, "Assign Privileges", {
        **_OKTA_TARGET_USER, "privileges": {"path": "target[type=ROLE].displayName", "transform": "list"}})),
    _route("privilege_revoke", {"in": ["user.account.privilege.revoke"]}, 3005, _okta(2, "Revoke Privileges", {
        **_OKTA_TARGET_USER, "privileges": {"path": "target[type=ROLE].displayName", "transform": "list"}})),
    _route("app_assign", {"in": ["application.user_membership.add"]}, 3005,
           _okta(1, "Assign Privileges", {**_OKTA_TARGET_USER, **_APP_RESOURCE})),
    _route("app_unassign", {"in": ["application.user_membership.remove"]}, 3005,
           _okta(2, "Revoke Privileges", {**_OKTA_TARGET_USER, **_APP_RESOURCE})),
    _route("app_assignment_other", {"prefix": ["application.user_membership."]}, 3005,
           _okta(99, "Other", {**_OKTA_TARGET_USER, **_APP_RESOURCE})),
    _route("oauth_consent", {"prefix": ["app.oauth2.admin.consent.", "app.oauth2.as.consent."]}, 3005, _okta(1, "Assign Privileges", {
        "privileges": {"path": "target[type=ConsentGrant].displayName", "transform": "list"},
        "resource.uid": "target[0].id", "resource.name": "target[0].displayName", "resource.type": "target[0].type"})),

    _route("account_other", {"prefix": ["user.account.", "user.lifecycle.", "user.mfa."]}, 3001,
           _okta(99, "Other", _OKTA_TARGET_USER)),

    # ── Group Management (3006)
    _route("group_add_user", {"in": ["group.user_membership.add"]}, 3006, _okta(3, "Add User", {**_OKTA_TARGET_USER, **_GROUP})),
    _route("group_remove_user", {"in": ["group.user_membership.remove"]}, 3006,
           _okta(4, "Remove User", {**_OKTA_TARGET_USER, **_GROUP})),
    _route("group_create", {"in": ["group.lifecycle.create"]}, 3006, _okta(6, "Create", _GROUP)),
    _route("group_delete", {"in": ["group.lifecycle.delete"]}, 3006, _okta(5, "Delete", _GROUP)),
    _route("group_privilege_grant", {"in": ["group.privilege.grant"]}, 3006, _okta(1, "Assign Privileges", _GROUP)),
    _route("group_privilege_revoke", {"in": ["group.privilege.revoke"]}, 3006, _okta(2, "Revoke Privileges", _GROUP)),
    _route("group_other", {"prefix": ["group."]}, 3006, _okta(9, "Update", _GROUP)),

    # ── Notifications are not entity changes
    _route("notification", {"prefix": ["system.email.", "system.sms.", "system.voice."]}, 0, _okta(99, "Other", {})),

    # ── Entity Management (3004): admin/configuration changes, activity by verb
    _route("entity_enroll", {"prefix": ["device.enrollment."]}, 3004, _okta(6, "Enroll", _ENTITY)),
    _route("entity_create", {"prefix": _ADMIN_PREFIXES, "suffix": [".create", ".add", ".created", ".bootstrap"]},
           3004, _okta(1, "Create", _ENTITY)),
    _route("entity_delete", {"prefix": _ADMIN_PREFIXES, "suffix": [".delete", ".remove", ".deleted"]},
           3004, _okta(4, "Delete", _ENTITY)),
    _route("entity_activate", {"prefix": _ADMIN_PREFIXES, "suffix": [".activate"]}, 3004, _okta(10, "Activate", _ENTITY)),
    _route("entity_deactivate", {"prefix": _ADMIN_PREFIXES, "suffix": [".deactivate"]}, 3004, _okta(11, "Deactivate", _ENTITY)),
    _route("entity_update", {"prefix": _ADMIN_PREFIXES}, 3004, _okta(3, "Update", _ENTITY)),
]


@register_connector
class OktaConnector(BaseConnector):
    meta = ConnectorMeta(
        type_id="okta",
        display_name="Okta",
        description="Ingest authentication and user lifecycle events from Okta's System Log API",
        icon="shield",
        category="identity",
        auth_methods=["api_key"],
        supports_polling=True,
        supports_webhook=True,
        default_ocsf_class_uid=3002,
        config_schema={
            "properties": {
                "domain": {"type": "string", "title": "Okta Domain", "placeholder": "your-org.okta.com"},
                "api_token": {"type": "string", "title": "API Token", "secret": True},
                "event_types": {
                    "type": "array",
                    "title": "Event Types",
                    "items": {"type": "string"},
                    "default": ["user.session.start", "user.authentication.sso", "user.lifecycle.create"],
                },
                "poll_interval_seconds": {"type": "integer", "title": "Poll Interval (s)", "default": 60},
            },
            "required": ["domain", "api_token"],
        },
        default_mapping={
            # Core event identity
            "metadata.uid": "uuid",
            "time": "published",
            "activity_name": "eventType",
            "message": "displayMessage",
            "severity_id": {"path": "severity", "transform": "lower"},
            # Actor (who did it)
            "actor.user.uid": "actor.id",
            "actor.user.name": "actor.alternateId",
            "actor.user.full_name": "actor.displayName",
            "actor.user.type": "actor.type",
            # Client / source endpoint
            "src_endpoint.ip": "client.ipAddress",
            "src_endpoint.location.city": "client.geographicalContext.city",
            "src_endpoint.location.country": "client.geographicalContext.country",
            "src_endpoint.location.postal_code": "client.geographicalContext.postalCode",
            "src_endpoint.location.lat": "client.geographicalContext.geolocation.lat",
            "src_endpoint.location.long": "client.geographicalContext.geolocation.lon",
            "http_request.user_agent": "client.userAgent.rawUserAgent",
            "src_endpoint.os": "client.userAgent.os",
            # Outcome / status
            "status_id": {"path": "outcome.result", "transform": "lower"},
            "status_detail": "outcome.reason",
            # Target (who was acted on)
            "dst_endpoint.uid": "target[0].id",
            "dst_endpoint.name": "target[0].displayName",
            "dst_endpoint.type": "target[0].type",
            # Authentication context
            "auth_protocol": "authenticationContext.authenticationProvider",
            "credential_uid": "authenticationContext.credentialType",
            # Session / transaction
            "session.uid": "transaction.id",
            # Request context
            "http_request.url.path": "debugContext.debugData.requestUri",
            # Each eventType family maps to its own OCSF class; anything unrecognised becomes a Base Event
            "_routes": OKTA_EVENT_ROUTES,
            "_default_class_uid": 0,
        },
    )

    def _domain(self) -> str:
        # Accept pasted URLs like "https://org-admin.okta.com/" — the API lives on the non-admin host
        domain = self.config["domain"].strip()
        domain = domain.removeprefix("https://").removeprefix("http://").split("/")[0]
        return domain.replace("-admin.", ".", 1)

    async def validate_config(self) -> tuple[bool, str]:
        if not self.config.get("domain"):
            return False, "domain is required"
        if not self.config.get("api_token"):
            return False, "api_token is required"
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        domain = self._domain()
        token = self.config["api_token"]
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"https://{domain}/api/v1/logs?limit=1",
                    headers={"Authorization": f"SSWS {token}", "Accept": "application/json"},
                )
                if resp.status_code == 200:
                    return True, "Connection successful"
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                return False, str(e)

    async def fetch_events(self, since: str | None = None) -> list[dict]:
        domain = self._domain()
        token = self.config["api_token"]
        params = {"limit": 1000, "sortOrder": "ASCENDING"}
        if since:
            params["since"] = since

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://{domain}/api/v1/logs",
                headers={"Authorization": f"SSWS {token}", "Accept": "application/json"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def handle_webhook(self, payload: dict, headers: dict) -> list[dict]:
        events = payload.get("data", {}).get("events", [])
        return events if events else [payload]
