from pydantic import BaseModel

from vox.models.base import VoxModel


class VoiceJoinRequest(BaseModel):
    self_mute: bool = False
    self_deaf: bool = False


class VoiceMemberData(VoxModel):
    user_id: int
    mute: bool
    deaf: bool
    video: bool
    streaming: bool
    server_mute: bool = False
    server_deaf: bool = False
    joined_at: int | None = None


class VoiceJoinResponse(VoxModel):
    media_url: str
    media_token: str
    members: list[VoiceMemberData]


class VoiceKickRequest(BaseModel):
    user_id: int


class VoiceMoveRequest(BaseModel):
    user_id: int
    to_room_id: int


class StageInviteRequest(BaseModel):
    user_id: int


class StageInviteResponseRequest(BaseModel):
    accepted: bool


class StageRevokeRequest(BaseModel):
    user_id: int


class VoiceServerMuteRequest(BaseModel):
    user_id: int
    muted: bool


class VoiceServerDeafenRequest(BaseModel):
    user_id: int
    deafened: bool


class StageTopicRequest(BaseModel):
    topic: str
