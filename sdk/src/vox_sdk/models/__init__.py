"""SDK response models."""

from vox_sdk.models.base import VoxModel
from vox_sdk.models.errors import ErrorCode, ErrorResponse

from vox_sdk.models.auth import (
    LoginResponse,
    MFARequiredResponse,
    MFASetupConfirmResponse,
    MFASetupResponse,
    MFAStatusResponse,
    RegisterResponse,
    SessionInfo,
    SessionListResponse,
    SuccessResponse,
    WebAuthnChallengeResponse,
    WebAuthnCredentialResponse,
)
from vox_sdk.models.bots import (
    CommandListResponse,
    CommandParam,
    CommandResponse,
    Embed,
    EmbedField,
    OkResponse,
    WebhookListItem,
    WebhookListWrapper,
    WebhookResponse,
)
from vox_sdk.models.channels import (
    CategoryListResponse,
    CategoryResponse,
    FeedResponse,
    PermissionOverrideOutput,
    RoomResponse,
    ThreadListResponse,
    ThreadResponse,
)
from vox_sdk.models.dms import DMListResponse, DMResponse
from vox_sdk.models.e2ee import (
    AddDeviceResponse,
    DeviceInfo,
    DeviceListResponse,
    DevicePrekey,
    KeyBackupResponse,
    PairDeviceResponse,
    PrekeyBundleResponse,
)
from vox_sdk.models.emoji import (
    EmojiListResponse,
    EmojiResponse,
    StickerListResponse,
    StickerResponse,
)
from vox_sdk.models.federation import (
    FederatedDevicePrekey,
    FederatedPrekeyResponse,
    FederatedUserProfile,
    FederationJoinResponse,
)
from vox_sdk.models.files import FileResponse
from vox_sdk.models.invites import (
    InviteListResponse,
    InvitePreviewResponse,
    InviteResponse,
)
from vox_sdk.models.members import (
    BanListResponse,
    BanResponse,
    MemberListResponse,
    MemberResponse,
)
from vox_sdk.models.messages import (
    EditMessageResponse,
    MessageListResponse,
    MessageResponse,
    ReactionGroup,
    ReactionListResponse,
    SearchResponse,
    SendMessageResponse,
)
from vox_sdk.models.moderation import (
    AuditLogEntry,
    AuditLogResponse,
    ReportDetailResponse,
    ReportListResponse,
    ReportResponse,
)
from vox_sdk.models.roles import RoleListResponse, RoleResponse
from vox_sdk.models.server import (
    CategoryInfo,
    FeedInfo,
    GatewayInfoResponse,
    PermissionOverrideData,
    RoomInfo,
    ServerInfoResponse,
    ServerLayoutResponse,
)
from vox_sdk.models.sync import ReadState, SyncEvent, SyncResponse
from vox_sdk.models.users import (
    BlockListResponse,
    DMSettingsResponse,
    FriendListResponse,
    FriendResponse,
    PresenceResponse,
    UserResponse,
)
from vox_sdk.models.voice import (
    MediaCertResponse,
    MediaTokenResponse,
    StageTopicResponse,
    VoiceJoinResponse,
    VoiceMemberData,
    VoiceMembersResponse,
)

__all__ = [
    "VoxModel",
    "ErrorCode",
    "ErrorResponse",
    # auth
    "LoginResponse",
    "MFARequiredResponse",
    "MFASetupConfirmResponse",
    "MFASetupResponse",
    "MFAStatusResponse",
    "RegisterResponse",
    "SessionInfo",
    "SessionListResponse",
    "SuccessResponse",
    "WebAuthnChallengeResponse",
    "WebAuthnCredentialResponse",
    # bots
    "CommandListResponse",
    "CommandParam",
    "CommandResponse",
    "Embed",
    "EmbedField",
    "OkResponse",
    "WebhookListItem",
    "WebhookListWrapper",
    "WebhookResponse",
    # channels
    "CategoryListResponse",
    "CategoryResponse",
    "FeedResponse",
    "PermissionOverrideOutput",
    "RoomResponse",
    "ThreadListResponse",
    "ThreadResponse",
    # dms
    "DMListResponse",
    "DMResponse",
    # e2ee
    "AddDeviceResponse",
    "DeviceInfo",
    "DeviceListResponse",
    "DevicePrekey",
    "KeyBackupResponse",
    "PairDeviceResponse",
    "PrekeyBundleResponse",
    # emoji
    "EmojiListResponse",
    "EmojiResponse",
    "StickerListResponse",
    "StickerResponse",
    # federation
    "FederatedDevicePrekey",
    "FederatedPrekeyResponse",
    "FederatedUserProfile",
    "FederationJoinResponse",
    # files
    "FileResponse",
    # invites
    "InviteListResponse",
    "InvitePreviewResponse",
    "InviteResponse",
    # members
    "BanListResponse",
    "BanResponse",
    "MemberListResponse",
    "MemberResponse",
    # messages
    "EditMessageResponse",
    "MessageListResponse",
    "MessageResponse",
    "ReactionGroup",
    "ReactionListResponse",
    "SearchResponse",
    "SendMessageResponse",
    # moderation
    "AuditLogEntry",
    "AuditLogResponse",
    "ReportDetailResponse",
    "ReportListResponse",
    "ReportResponse",
    # roles
    "RoleListResponse",
    "RoleResponse",
    # server
    "CategoryInfo",
    "FeedInfo",
    "GatewayInfoResponse",
    "PermissionOverrideData",
    "RoomInfo",
    "ServerInfoResponse",
    "ServerLayoutResponse",
    # sync
    "ReadState",
    "SyncEvent",
    "SyncResponse",
    # users
    "BlockListResponse",
    "DMSettingsResponse",
    "FriendListResponse",
    "FriendResponse",
    "PresenceResponse",
    "UserResponse",
    # voice
    "MediaCertResponse",
    "MediaTokenResponse",
    "StageTopicResponse",
    "VoiceJoinResponse",
    "VoiceMemberData",
    "VoiceMembersResponse",
]
