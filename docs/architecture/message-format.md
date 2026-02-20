# Message Body Format

Message bodies are UTF-8 strings that may contain a subset of Markdown
formatting and special mention syntax. The server stores and transmits message
bodies **as-is** -- it does not parse or validate Markdown. Rendering is
entirely the client's responsibility.

---

## Supported Markdown Subset

| Syntax | Renders As | Example |
|---|---|---|
| `*text*` | *Italic* | `*hello*` |
| `**text**` | **Bold** | `**hello**` |
| `~~text~~` | ~~Strikethrough~~ | `~~hello~~` |
| `` `code` `` | `Inline code` | `` `hello` `` |
| ` ```code``` ` | Code block | See below |
| `> text` | Block quote | `> hello` |
| `[text](url)` | Hyperlink | `[Vox](https://example.com)` |
| `\|\|text\|\|` | Spoiler (hidden until clicked) | `\|\|secret\|\|` |

### Code Blocks

Fenced code blocks use triple backticks with an optional language hint:

````
```python
print("hello")
```
````

### Block Quotes

Lines prefixed with `>` are rendered as block quotes. Multiple consecutive
quoted lines form a single quote block.

```
> This is a quote.
> It spans two lines.
```

---

## Mention Syntax

Mentions are encoded inline using angle-bracket syntax. Clients should
resolve the IDs and render them as highlighted names.

| Syntax | Target | Example |
|---|---|---|
| `<@user_id>` | A specific user | `<@42>` |
| `<@&role_id>` | A specific role | `<@&7>` |
| `<@everyone>` | All members with access | `<@everyone>` |

### Rendering

- `<@42>` should resolve to the user's display name and render with a
  highlight, e.g. **@Alice**.
- `<@&7>` should resolve to the role name and render with the role's colour,
  e.g. **@Moderators**.
- `<@everyone>` should render as a highlighted **@everyone** tag and notify
  all members who can see the feed (subject to the `MENTION_EVERYONE`
  permission).

---

## Server Behaviour

The server treats the message body as an opaque string:

- No Markdown validation or sanitisation is performed.
- No mention resolution is performed server-side.
- The body is stored and relayed exactly as the client sent it.
- For E2E-encrypted messages, the body may be stored in the `opaque_blob`
  field as an encrypted byte string; the `body` field will be `null`.

Clients must handle malformed Markdown gracefully -- unknown syntax should be
rendered as plain text.
