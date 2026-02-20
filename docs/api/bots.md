# Bots and Commands

Endpoints for bot command registration, interaction handling, and component dispatch.

All endpoints are under `/api/v1/` and require a Bearer token (bot token).

---

## Bot Types

Vox supports two types of bots and webhooks for programmatic integration:

| Capability           | Gateway Bot                      | HTTP-Only Bot                    | Webhook                       |
|----------------------|----------------------------------|----------------------------------|-------------------------------|
| **Connection**       | WebSocket (gateway)              | Receives HTTP POSTs              | Sends HTTP POSTs              |
| **Events**           | All gateway events               | Interactions only                | None (send-only)              |
| **Commands**         | Yes                              | Yes                              | No                            |
| **Components**       | Yes                              | Yes                              | No                            |
| **Presence**         | Online while connected           | No presence                      | No presence                   |
| **Auth**             | Bot token                        | Bot token + `interaction_url`    | Webhook token in URL          |
| **Use case**         | Full-featured bots               | Lightweight slash commands       | External service notifications|

**Gateway bots** connect via WebSocket and receive all events in real time, like a user client.

**HTTP-only bots** register an `interaction_url` during setup. When a user triggers a slash command or component interaction, the server POSTs the interaction payload to that URL.

---

## Slash Command Flow

1. A user types `/command` in a feed.
2. The server parses the command and parameters.
3. An `interaction_create` event is dispatched to the bot (via gateway or HTTP POST to `interaction_url`).
4. The bot responds by calling `POST /interactions/{interaction_id}/response`.

```
User -> /weather london
         |
         v
Server: parse command, resolve bot
         |
         v
Bot receives interaction_create:
{
  "interaction_id": "950000000000001",
  "command": "weather",
  "params": {"city": "london"},
  "user_id": "100000000000042",
  "feed_id": "300000000000001"
}
         |
         v
Bot calls POST /interactions/950000000000001/response
```

---

## Component Interaction Flow

Messages can contain interactive components (buttons, select menus). When a user interacts with a component:

1. The client sends `POST /interactions/component` with the message ID and component ID.
2. The server resolves which bot owns the component and dispatches the interaction.
3. The bot responds via the interaction response endpoint.

---

## Register Commands

Register or update slash commands for your bot.

```
PUT /bots/@me/commands
```

### Request Body

```json
{
  "commands": [
    {
      "name": "weather",
      "description": "Get the current weather for a city",
      "params": [
        {
          "name": "city",
          "description": "City name",
          "type": "string",
          "required": true
        },
        {
          "name": "units",
          "description": "Temperature units",
          "type": "string",
          "required": false,
          "choices": ["celsius", "fahrenheit"]
        }
      ]
    },
    {
      "name": "ping",
      "description": "Check if the bot is alive",
      "params": []
    }
  ]
}
```

| Field                  | Type     | Required | Description                          |
|------------------------|----------|----------|--------------------------------------|
| `commands`             | object[] | Yes      | Array of command definitions         |
| `commands[].name`      | string   | Yes      | Command name (lowercase, no spaces)  |
| `commands[].description` | string | Yes      | Short description shown to users     |
| `commands[].params`    | object[] | Yes      | Parameter definitions (can be empty) |
| `params[].name`        | string   | Yes      | Parameter name                       |
| `params[].description` | string   | Yes      | Parameter description                |
| `params[].type`        | string   | Yes      | `string`, `integer`, `boolean`, `user`, `feed`, `role` |
| `params[].required`    | boolean  | Yes      | Whether the parameter is required    |
| `params[].choices`     | string[] | No       | Restrict input to these values       |

### Response `200 OK`

```json
{
  "commands": [
    {
      "name": "weather",
      "description": "Get the current weather for a city",
      "params": [
        {"name": "city", "description": "City name", "type": "string", "required": true, "choices": null},
        {"name": "units", "description": "Temperature units", "type": "string", "required": false, "choices": ["celsius", "fahrenheit"]}
      ]
    },
    {
      "name": "ping",
      "description": "Check if the bot is alive",
      "params": []
    }
  ]
}
```

---

## Delete Commands

```
DELETE /bots/@me/commands
```

### Request Body

```json
{
  "command_names": ["weather"]
}
```

### Response `204 No Content`

---

## List Available Commands

List all registered commands available in the current context.

```
GET /commands
```

### Response `200 OK`

```json
{
  "commands": [
    {
      "name": "weather",
      "description": "Get the current weather for a city",
      "bot_id": "100000000000200",
      "params": [
        {"name": "city", "description": "City name", "type": "string", "required": true, "choices": null},
        {"name": "units", "description": "Temperature units", "type": "string", "required": false, "choices": ["celsius", "fahrenheit"]}
      ]
    },
    {
      "name": "ping",
      "description": "Check if the bot is alive",
      "bot_id": "100000000000200",
      "params": []
    }
  ]
}
```

---

## Respond to Interaction

Send a response to a slash command or component interaction.

```
POST /interactions/{interaction_id}/response
```

### Request Body

```json
{
  "body": "The weather in London is 12C and cloudy.",
  "embeds": [
    {
      "title": "London Weather",
      "description": "Temperature: 12C\nCondition: Cloudy\nHumidity: 78%",
      "image": "https://weather.example/icons/cloudy.png"
    }
  ],
  "components": [
    {
      "type": "button",
      "label": "Refresh",
      "component_id": "weather_refresh_london"
    }
  ],
  "ephemeral": false
}
```

| Field       | Type     | Required | Description                                        |
|-------------|----------|----------|----------------------------------------------------|
| `body`      | string   | Yes      | Response message content                           |
| `embeds`    | object[] | No       | Embed objects                                      |
| `components`| object[] | No       | Interactive components to attach to the response   |
| `ephemeral` | boolean  | No       | If `true`, only the invoking user sees the response|

### Response `200 OK`

```json
{
  "msg_id": "419870123457000",
  "timestamp": "2026-02-19T12:30:00Z"
}
```

---

## Submit Component Interaction

Triggered when a user clicks a button or selects from a menu on a message.

```
POST /interactions/component
```

### Request Body

```json
{
  "msg_id": "419870123457000",
  "component_id": "weather_refresh_london"
}
```

### Response `204 No Content`

The server dispatches the interaction to the owning bot, which then responds via `POST /interactions/{interaction_id}/response`.

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body or command definition       |
| `403`  | Bot lacks required permissions                   |
| `404`  | Interaction or command not found                 |
| `408`  | Bot did not respond to interaction in time       |
| `429`  | Rate limited                                     |
