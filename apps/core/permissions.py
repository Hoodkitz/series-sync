"""Permissions."""
from enum import Enum
from typing import Set


class Permission(str, Enum):
    READ_JOB = "read:job"
    CREATE_JOB = "create:job"
    UPDATE_JOB = "update:job"
    CANCEL_JOB = "cancel:job"
    READ_VOICE = "read:voice"
    CREATE_VOICE = "create:voice"
    UPDATE_VOICE = "update:voice"
    DELETE_VOICE = "delete:voice"
    UPLOAD_FILE = "upload:file"
    EXPORT = "export"
    EXPORT_QA = "export:qa"


class Role(str, Enum):
    USER = "user"
    ADMIN = "admin"
    AGENT = "agent"
    AUDIT = "audit"


PERMISSIONS: dict[Role, set[str]] = {
    Role.USER: {
        Permission.READ_JOB, Permission.CREATE_JOB, Permission.UPDATE_JOB,
        Permission.UPLOAD_FILE, Permission.EXPORT,
    },
    Role.ADMIN: {
        Permission.READ_JOB, Permission.CREATE_JOB, Permission.UPDATE_JOB,
        Permission.CANCEL_JOB, Permission.UPLOAD_FILE, Permission.EXPORT,
        Permission.EXPORT_QA,
    },
    Role.AGENT: {
        Permission.READ_JOB, Permission.CREATE_JOB, Permission.UPDATE_JOB,
        Permission.READ_VOICE, Permission.CREATE_VOICE, Permission.UPDATE_VOICE,
        Permission.EXPORT,
    },
    Role.AUDIT: {
        Permission.READ_JOB, Permission.READ_VOICE, Permission.EXPORT,
    },
}
