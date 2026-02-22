from enum import Enum


class FeedType(str, Enum):
    text = "text"
    forum = "forum"
    announcement = "announcement"


class RoomType(str, Enum):
    voice = "voice"
    stage = "stage"


class OverrideTargetType(str, Enum):
    role = "role"
    user = "user"


class DMPermission(str, Enum):
    everyone = "everyone"
    friends_only = "friends_only"
    mutual_servers = "mutual_servers"
    nobody = "nobody"
