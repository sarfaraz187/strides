from mcp.server.auth.middleware.auth_context import get_access_token


def current_user_id() -> str:
    access_token = get_access_token()
    if access_token is None or access_token.subject is None:
        raise PermissionError("No authenticated user")
    return access_token.subject
