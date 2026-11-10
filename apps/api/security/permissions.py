from fastapi import Depends, HTTPException, status
from apps.db.models import User
from apps.api.security.auth import get_current_active_user
from apps.core.permissions import Role, PERMISSIONS, Permission

def check_permission(required_permission: Permission):
    def permission_dependency(current_user: User = Depends(get_current_active_user)):
        user_role = Role(current_user.role)
        if required_permission not in PERMISSIONS.get(user_role, set()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    return permission_dependency
