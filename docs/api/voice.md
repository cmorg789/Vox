# Voice and Stage

Endpoints for joining, leaving, and managing voice rooms and stage rooms.

All endpoints are under `/api/v1/` and require a Bearer token.

---

## Join Voice Room

Connect to a voice room. Returns the media server URL, a short-lived media token, and the current member list.

```
POST /rooms/{room_id}/voice/join
```

### Request Body

```json
{
  "self_mute": false,
  "self_deaf": false
}
```

| Field       | Type    | Required | Description                    |
|-------------|---------|----------|--------------------------------|
| `self_mute` | boolean | Yes      | Join with microphone muted     |
| `self_deaf` | boolean | Yes      | Join with audio deafened       |

### Response `200 OK`

```json
{
  "media_url": "wss://media.vox.example/v1",
  "media_token": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9...",
  "members": [
    {
      "user_id": "100000000000042",
      "username": "alice",
      "self_mute": false,
      "self_deaf": false,
      "server_mute": false,
      "server_deaf": false
    },
    {
      "user_id": "100000000000099",
      "username": "bob",
      "self_mute": true,
      "self_deaf": false,
      "server_mute": false,
      "server_deaf": false
    }
  ]
}
```

The `media_token` is short-lived. When it approaches expiry the gateway dispatches a `media_token_refresh` event with a new token:

```json
{
  "event": "media_token_refresh",
  "data": {
    "room_id": "400000000000001",
    "media_token": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.new..."
  }
}
```

---

## Leave Voice Room

```
POST /rooms/{room_id}/voice/leave
```

### Response `204 No Content`

---

## Kick from Voice

Disconnect a user from the voice room.

```
POST /rooms/{room_id}/voice/kick
```

**Required Permission:** `MOVE_MEMBERS` or `MUTE_MEMBERS`

### Request Body

```json
{
  "user_id": "100000000000099"
}
```

### Response `204 No Content`

---

## Move User to Another Room

Move a user from the current voice room to a different one.

```
POST /rooms/{room_id}/voice/move
```

**Required Permission:** `MOVE_MEMBERS`

### Request Body

```json
{
  "user_id": "100000000000099",
  "to_room_id": "400000000000002"
}
```

### Response `204 No Content`

---

## Stage Rooms

Stage rooms are special voice rooms where speaking is moderated. Members join as listeners and must request or be invited to speak.

### Request to Speak

```
POST /rooms/{room_id}/stage/request
```

### Response `204 No Content`

A `stage_request` gateway event is dispatched to stage moderators.

---

### Invite to Speak

Invite a listener to become a speaker.

```
POST /rooms/{room_id}/stage/invite
```

**Required Permission:** `STAGE_MODERATOR`

### Request Body

```json
{
  "user_id": "100000000000099"
}
```

### Response `204 No Content`

---

### Respond to Stage Invite

Accept or decline a stage invite.

```
POST /rooms/{room_id}/stage/invite/respond
```

### Request Body

```json
{
  "accepted": true
}
```

### Response `204 No Content`

---

### Revoke Speaker

Move a speaker back to the listener role.

```
POST /rooms/{room_id}/stage/revoke
```

**Required Permission:** `STAGE_MODERATOR`

### Request Body

```json
{
  "user_id": "100000000000099"
}
```

### Response `204 No Content`

---

### Update Stage Topic

```
PATCH /rooms/{room_id}/stage/topic
```

### Request Body

```json
{
  "topic": "Q&A with the dev team"
}
```

### Response `200 OK`

```json
{
  "room_id": "400000000000001",
  "topic": "Q&A with the dev team"
}
```

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body or parameters               |
| `403`  | Missing required permission                      |
| `404`  | Room not found                                   |
| `409`  | Already in the voice room / not in the room      |
| `429`  | Rate limited                                     |
