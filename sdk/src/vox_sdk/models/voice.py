from vox_sdk.models.base import VoxModel


class VoiceMemberData(VoxModel):
    user_id: int
    mute: bool = False
    deaf: bool = False
    video: bool = False
    streaming: bool = False
    server_mute: bool = False
    server_deaf: bool = False
    joined_at: int | None = None


class VoiceJoinResponse(VoxModel):
    media_url: str
    media_token: str
    members: list[VoiceMemberData] = []


class VoiceMembersResponse(VoxModel):
    room_id: int
    members: list[VoiceMemberData] = []


class MediaTokenResponse(VoxModel):
    media_token: str


class MediaCertResponse(VoxModel):
    fingerprint: str
    cert_der: list[int]


class StageTopicResponse(VoxModel):
    topic: str
