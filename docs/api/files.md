# Files

Endpoints for uploading and retrieving file attachments.

All endpoints are under `/api/v1/` and require a Bearer token unless noted otherwise.

---

## Upload File

Upload a file to attach to a message. Returns a file object whose `file_id` can be included in the `attachments` array when sending a message.

```
POST /feeds/{feed_id}/files
```

**Content-Type:** `multipart/form-data`

### Form Fields

| Field  | Type   | Required | Description                          |
|--------|--------|----------|--------------------------------------|
| `file` | binary | Yes      | The file content                     |
| `name` | string | Yes      | Display filename                     |
| `mime` | string | Yes      | MIME type (e.g., `image/png`)        |

### Example Request

```
POST /api/v1/feeds/300000000000001/files HTTP/1.1
Authorization: Bearer <token>
Content-Type: multipart/form-data; boundary=----VoxBoundary

------VoxBoundary
Content-Disposition: form-data; name="file"; filename="screenshot.png"
Content-Type: image/png

<binary data>
------VoxBoundary
Content-Disposition: form-data; name="name"

screenshot.png
------VoxBoundary
Content-Disposition: form-data; name="mime"

image/png
------VoxBoundary--
```

### Response `201 Created`

```json
{
  "file_id": "500000000000001",
  "name": "screenshot.png",
  "size": 204800,
  "mime": "image/png",
  "url": "https://cdn.vox.example/files/500000000000001"
}
```

Use the returned `file_id` in the `attachments` array when [sending a message](messages.md#send-message):

```json
{
  "body": "Here is the screenshot",
  "attachments": ["500000000000001"]
}
```

---

## Get File

Retrieve a file's content. The response includes the appropriate `Content-Type` header. The server may respond with a `302` redirect to a CDN URL.

```
GET /files/{file_id}
```

### Response `200 OK`

Binary file content with the correct `Content-Type` header.

```
HTTP/1.1 200 OK
Content-Type: image/png
Content-Length: 204800

<binary data>
```

### Response `302 Found` (CDN redirect)

```
HTTP/1.1 302 Found
Location: https://cdn.vox.example/files/500000000000001
```

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Missing or invalid form fields                   |
| `403`  | Missing permission to upload in this feed         |
| `404`  | File not found                                   |
| `413`  | File exceeds maximum allowed size                |
| `429`  | Rate limited                                     |
