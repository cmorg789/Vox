# Vox Protocol REST API

The Vox REST API provides programmatic access to a Vox server. All endpoints
are served under the `/api/v1/` base path and exchange JSON request and response
bodies unless otherwise noted.

Before diving into individual resources, read the
[Conventions](conventions.md) page -- it covers authentication, pagination,
error handling, rate limits, and ID formats that apply across every endpoint.

---

## API Sections

| Section | Description |
|---|---|
| [Conventions](conventions.md) | Base URL, authentication, pagination, error format, rate limits, ID spaces |
| [Authentication](authentication.md) | Register, login, logout, two-factor setup and verification, WebAuthn |
| [Users](users.md) | User profiles, presence, display-name / avatar updates, friends, blocks |
| [Server](server.md) | Server metadata, limits, and layout (categories, feeds, rooms) |
| [Members](members.md) | Member list, join / leave, nicknames, kicks, bans |
| [Channels](channels.md) | Feeds, rooms, categories, roles, and permission overrides |
