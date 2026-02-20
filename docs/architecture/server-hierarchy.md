# Server Hierarchy

A Vox server represents a single community. Everything a community needs --
channels, roles, members, emoji -- lives inside that server.

## Hierarchy Diagram

```
Server
 |
 +-- Members
 +-- Roles
 +-- Custom Emoji
 |
 +-- Category A
 |    +-- Feed (text)
 |    |    +-- Messages
 |    |    +-- Threads
 |    +-- Feed (forum)
 |    |    +-- Threads (top-level posts)
 |    +-- Feed (announcement)
 |    |    +-- Messages
 |    +-- Room (voice)
 |    |    +-- Participants
 |    +-- Room (stage)
 |         +-- Participants
 |
 +-- Category B
      +-- ...
```

## Entities

### Server

The top-level container. One server corresponds to one community. Each server
has its own domain, member list, role hierarchy, and emoji set.

### Categories

Categories are organisational folders that group **Feeds** and **Rooms**
together. They have no functional behaviour beyond grouping and ordering; they
do not carry their own permission overrides.

### Feeds

Feeds are text-based channels. Three feed types exist:

| Type | Description |
|---|---|
| **text** | Standard message stream. Members send messages and optionally create threads. |
| **forum** | Thread-first channel. Every top-level post is a thread; there is no flat message stream. |
| **announcement** | Read-heavy channel. Only privileged roles can post; other members read. |

Feeds contain **messages** and **threads**.

### Rooms

Rooms are real-time voice/video spaces. Two room types exist:

| Type | Description |
|---|---|
| **voice** | Open conversation. All connected participants can speak freely. |
| **stage** | Moderated conversation. Speakers are promoted by stage moderators; the audience listens. |

Rooms contain **participants** -- members who are currently connected and
sending or receiving media.

### Members

A member is a user who has joined the server. Each member can hold zero or more
roles and has a server-scoped nickname.

### Roles

Roles define a set of permissions (a 64-bit bitfield) and can be assigned to
members. Roles are evaluated in priority order during permission resolution.
Every server has an implicit `@everyone` role that applies to all members.

### Custom Emoji

Servers can upload custom emoji that members reference in messages. Emoji are
server-scoped and identified by a unique ID.
