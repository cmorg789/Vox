# Permission System

Vox uses a **64-bit bitfield** to represent permissions. Each bit corresponds
to a single permission. Roles, overrides, and the special Administrator bit
interact through a well-defined resolution order.

---

## Permission Bits

### General & Channel Permissions (bits 0--19)

| Bit | Name | Description |
|----:|------|-------------|
| 0 | `VIEW_SPACE` | View feeds and rooms in a category |
| 1 | `SEND_MESSAGES` | Send messages in text feeds |
| 2 | `SEND_EMBEDS` | Send rich embeds / link previews |
| 3 | `ATTACH_FILES` | Upload file attachments |
| 4 | `ADD_REACTIONS` | Add emoji reactions to messages |
| 5 | `READ_HISTORY` | Read message history |
| 6 | `MENTION_EVERYONE` | Use `@everyone` mentions |
| 7 | `USE_EXTERNAL_EMOJI` | Use emoji from other servers |
| 8 | `CONNECT` | Connect to voice / stage rooms |
| 9 | `SPEAK` | Transmit audio in voice rooms |
| 10 | `VIDEO` | Transmit video in voice rooms |
| 11 | `MUTE_MEMBERS` | Server-mute other members in voice |
| 12 | `DEAFEN_MEMBERS` | Server-deafen other members in voice |
| 13 | `MOVE_MEMBERS` | Move members between voice rooms |
| 14 | `PRIORITY_SPEAKER` | Transmit with elevated audio priority |
| 15 | `STREAM` | Go live / screen share in a room |
| 16 | `STAGE_MODERATOR` | Manage speakers on a stage |
| 17 | `CREATE_THREADS` | Create new threads in feeds |
| 18 | `MANAGE_THREADS` | Edit, archive, and delete threads |
| 19 | `SEND_IN_THREADS` | Send messages inside threads |

### Reserved (bits 20--23)

Bits 20--23 are reserved for future general/channel permissions.

### Administrative Permissions (bits 24--37)

| Bit | Name | Description |
|----:|------|-------------|
| 24 | `MANAGE_SPACES` | Create, edit, and delete categories, feeds, and rooms |
| 25 | `MANAGE_ROLES` | Create, edit, and delete roles below yours |
| 26 | `MANAGE_EMOJI` | Upload, edit, and delete custom emoji |
| 27 | `MANAGE_WEBHOOKS` | Create, edit, and delete webhooks |
| 28 | `MANAGE_SERVER` | Edit server name, icon, and settings |
| 29 | `KICK_MEMBERS` | Remove members from the server |
| 30 | `BAN_MEMBERS` | Permanently ban members |
| 31 | `CREATE_INVITES` | Create invite links |
| 32 | `CHANGE_NICKNAME` | Change your own nickname |
| 33 | `MANAGE_NICKNAMES` | Change other members' nicknames |
| 34 | `VIEW_AUDIT_LOG` | View the server audit log |
| 35 | `MANAGE_MESSAGES` | Delete and pin other members' messages |
| 36 | `VIEW_REPORTS` | View member reports |
| 37 | `MANAGE_2FA` | Manage server-level 2FA requirements |

### Reserved (bits 38--62)

Bits 38--62 are reserved for future administrative permissions.

### Special (bit 63)

| Bit | Name | Description |
|----:|------|-------------|
| 63 | `ADMINISTRATOR` | Bypasses **all** permission checks |

---

## Permission Resolution

Permissions are resolved in the following order. Each step builds on the
previous result.

```
 1. Start with @everyone role permissions           (base)
 2. OR all of the user's role permissions            (cumulative grant)
 3. Apply feed/room @everyone permission overrides   (allow/deny)
 4. Apply feed/room role-specific overrides           (allow/deny)
 5. Apply feed/room user-specific override            (allow/deny)
 6. If ADMINISTRATOR bit is set, grant everything
```

### Step-by-step

1. **@everyone base** -- Every server has an implicit `@everyone` role. Its
   permission bitfield is the starting point.

2. **User role union** -- The permission bitfields of every role assigned to
   the user are bitwise-ORed together with the base. This can only *add*
   permissions, never remove them.

3. **Feed/room @everyone overrides** -- A feed or room may define an override
   for the `@everyone` role. The override contains an `allow` bitfield and a
   `deny` bitfield. Denied bits are cleared; allowed bits are set.

4. **Feed/room role overrides** -- The feed or room may define overrides for
   specific roles. For each role the user holds, the allow/deny bitfields are
   combined (deny bits across all matching roles are unioned, then allow bits
   are unioned). Denied bits are cleared first, then allowed bits are set.

5. **Feed/room user-specific override** -- A per-user override on the feed or
   room. Deny bits are cleared; allow bits are set. This is the most specific
   override and takes final precedence.

6. **Administrator bypass** -- If the resulting bitfield has bit 63
   (`ADMINISTRATOR`) set, the user is granted all permissions regardless of
   the computed value.

### Example

```python
# Pseudocode
perms  = everyone_role.permissions

for role in user.roles:
    perms |= role.permissions

# @everyone channel override
perms &= ~channel_everyone_override.deny
perms |=  channel_everyone_override.allow

# Role channel overrides (combined)
role_deny  = 0
role_allow = 0
for role in user.roles:
    if role.id in channel_overrides:
        role_deny  |= channel_overrides[role.id].deny
        role_allow |= channel_overrides[role.id].allow
perms &= ~role_deny
perms |=  role_allow

# User-specific channel override
if user.id in channel_overrides:
    perms &= ~channel_overrides[user.id].deny
    perms |=  channel_overrides[user.id].allow

# Administrator bypass
if perms & (1 << 63):
    perms = ALL_PERMISSIONS
```
