# Moderation

Endpoints for user reports, audit logs, and administrative actions.

All endpoints are under `/api/v1/` and require a Bearer token.

---

## Submit Report

Report a user for violating community guidelines. For E2EE DMs, the client decrypts messages locally and submits the plaintext voluntarily.

```
POST /reports
```

### Request Body

```json
{
  "reported_user_id": "100000000000099",
  "dm_id": "800000000000001",
  "messages": [
    {
      "msg_id": "419870123456810",
      "body": "The plaintext content of the reported message",
      "timestamp": "2026-02-19T11:00:00Z"
    },
    {
      "msg_id": "419870123456811",
      "body": "Another offending message",
      "timestamp": "2026-02-19T11:01:00Z"
    }
  ],
  "reason": "harassment",
  "description": "User has been sending repeated unwanted messages after being asked to stop."
}
```

| Field              | Type     | Required | Description                                   |
|--------------------|----------|----------|-----------------------------------------------|
| `reported_user_id` | string   | Yes      | ID of the user being reported                 |
| `dm_id`            | string   | No       | DM ID if the report concerns DM messages      |
| `messages`         | object[] | Yes      | Array of message objects as evidence           |
| `reason`           | string   | Yes      | Reason category (see below)                   |
| `description`      | string   | Yes      | Free-text description of the issue             |

### Reason Categories

| Value             | Description                              |
|-------------------|------------------------------------------|
| `harassment`      | Targeted harassment or bullying          |
| `spam`            | Spam or unsolicited advertising          |
| `illegal_content` | Content that violates applicable law     |
| `threats`         | Threats of violence or harm              |
| `other`           | Other violations not covered above       |

### Response `201 Created`

```json
{
  "report_id": "950000000000001",
  "reported_user_id": "100000000000099",
  "reporter_id": "100000000000042",
  "reason": "harassment",
  "status": "open",
  "created_at": "2026-02-19T12:00:00Z"
}
```

---

## List Reports

```
GET /reports
```

**Required Permission:** `VIEW_REPORTS`

### Query Parameters

| Parameter | Type   | Default | Description                      |
|-----------|--------|---------|----------------------------------|
| `status`  | string | —       | Filter by status: `open`, `resolved` |
| `limit`   | int    | `50`    | Number of reports to return      |
| `cursor`  | string | —       | Pagination cursor                |

### Response `200 OK`

```json
{
  "reports": [
    {
      "report_id": "950000000000001",
      "reported_user_id": "100000000000099",
      "reporter_id": "100000000000042",
      "reason": "harassment",
      "description": "User has been sending repeated unwanted messages after being asked to stop.",
      "messages": [
        {
          "msg_id": "419870123456810",
          "body": "The plaintext content of the reported message",
          "timestamp": "2026-02-19T11:00:00Z"
        }
      ],
      "status": "open",
      "created_at": "2026-02-19T12:00:00Z",
      "resolved_at": null,
      "resolved_by": null,
      "resolution_action": null
    }
  ],
  "cursor": "950000000000001"
}
```

---

## Resolve Report

```
POST /reports/{report_id}/resolve
```

**Required Permission:** `VIEW_REPORTS`

### Request Body

```json
{
  "action": "ban"
}
```

| Action    | Description                                      |
|-----------|--------------------------------------------------|
| `dismiss` | Close the report with no action taken            |
| `warn`    | Issue a warning to the reported user             |
| `kick`    | Remove the user from the server                  |
| `ban`     | Permanently ban the user from the server         |

### Response `200 OK`

```json
{
  "report_id": "950000000000001",
  "status": "resolved",
  "resolution_action": "ban",
  "resolved_by": "100000000000042",
  "resolved_at": "2026-02-19T13:00:00Z"
}
```

---

## Query Audit Log

Retrieve audit log entries for moderation and administrative actions.

```
GET /audit-log
```

**Required Permission:** `VIEW_AUDIT_LOG`

### Query Parameters

| Parameter    | Type   | Default | Description                                    |
|--------------|--------|---------|------------------------------------------------|
| `event_type` | string | —       | Filter by event type (dot-notation, see below) |
| `actor_id`   | string | —       | Filter by the user who performed the action    |
| `target_id`  | string | —       | Filter by the target of the action             |
| `before`     | string | —       | Return entries before this timestamp           |
| `after`      | string | —       | Return entries after this timestamp            |
| `limit`      | int    | `50`    | Number of entries to return (1--100)           |
| `cursor`     | string | —       | Pagination cursor                              |

### Event Types

Event types use dot-notation to organize categories:

| Event Type           | Description                          |
|----------------------|--------------------------------------|
| `member.kick`        | Member kicked from server            |
| `member.ban`         | Member banned                        |
| `member.unban`       | Member unbanned                      |
| `member.timeout`     | Member timed out                     |
| `role.create`        | Role created                         |
| `role.update`        | Role permissions or name changed     |
| `role.delete`        | Role deleted                         |
| `role.assign`        | Role assigned to a member            |
| `role.revoke`        | Role removed from a member           |
| `feed.create`        | Feed created                         |
| `feed.update`        | Feed settings changed                |
| `feed.delete`        | Feed deleted                         |
| `room.create`        | Voice room created                   |
| `room.update`        | Voice room settings changed          |
| `room.delete`        | Voice room deleted                   |
| `message.delete`     | Message deleted by moderator         |
| `message.bulk_delete`| Messages bulk-deleted                |
| `invite.create`      | Invite link created                  |
| `invite.delete`      | Invite link revoked                  |
| `webhook.create`     | Webhook created                      |
| `webhook.delete`     | Webhook deleted                      |
| `emoji.create`       | Custom emoji added                   |
| `emoji.delete`       | Custom emoji removed                 |
| `server.update`      | Server settings changed              |
| `twofa.reset`        | 2FA reset for a user                 |

### Example Request

```
GET /api/v1/audit-log?event_type=member.kick&actor_id=100000000000042&limit=10
```

### Response `200 OK`

```json
{
  "entries": [
    {
      "entry_id": "960000000000001",
      "event_type": "member.kick",
      "actor_id": "100000000000042",
      "target_id": "100000000000099",
      "reason": "Repeated spam in general feed",
      "metadata": {},
      "timestamp": "2026-02-19T11:30:00Z"
    },
    {
      "entry_id": "960000000000002",
      "event_type": "member.kick",
      "actor_id": "100000000000042",
      "target_id": "100000000000101",
      "reason": "Disruptive behavior",
      "metadata": {},
      "timestamp": "2026-02-18T16:45:00Z"
    }
  ],
  "cursor": "960000000000002"
}
```

---

## Admin 2FA Reset

Disable all two-factor authentication methods for a target user. This is an administrative action and is recorded in the audit log.

```
POST /admin/2fa-reset
```

**Required Permission:** `MANAGE_2FA`

### Request Body

```json
{
  "target_user_id": "100000000000099",
  "reason": "User lost access to their authenticator device and verified identity through support."
}
```

| Field            | Type   | Required | Description                              |
|------------------|--------|----------|------------------------------------------|
| `target_user_id` | string | Yes      | ID of the user whose 2FA will be disabled|
| `reason`         | string | Yes      | Reason for the reset (recorded in audit log)|

### Response `200 OK`

```json
{
  "target_user_id": "100000000000099",
  "twofa_disabled": true,
  "audit_entry_id": "960000000000010"
}
```

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body or parameters               |
| `403`  | Missing required permission                      |
| `404`  | Report or audit entry not found                  |
| `429`  | Rate limited                                     |
