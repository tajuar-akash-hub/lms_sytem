# Frontend

The frontend is a single file: **`index.html`**.

Everything (HTML, CSS, JavaScript) lives in this one file. It uses Tailwind via CDN, so there's no build step. You can edit it with any text editor.

## What you can change freely

| You want to... | Edit in `index.html` |
|---|---|
| Change colors / layout / spacing | The `<style>` block at the top |
| Add new buttons or sections | Anywhere in `<body>` |
| Change which API the frontend calls | The `API = ""` constant near the top of the `<script>` |
| Add new keyboard shortcuts, animations, etc. | The `<script>` block |
| Show a new field from the video summary | `renderMain()` function |

## What you should NOT change

- The **shape** of API calls (`fetchVideos`, `fetchVideo`, `postChat`) — these match what `app.py` returns.
- The YouTube IFrame API usage (`YT.Player`) — that's how videos are loaded.

## API endpoints the frontend uses

- `GET  /api/videos` → list of all processed videos (each has `id`, `source_id`, `title`, `summary.overview`, `summary.key_concepts`, `summary.suggested_questions`)
- `GET  /api/videos/{id}` → one video with full details
- `POST /api/videos/{id}/chat` → `{question: string, student_id: string}` → `{answer, cited_timestamp, cited_text}`

## Running locally

```bash
# From the project root, with the FastAPI server running:
#   python app.py
# Then open http://localhost:8000
```

## Separating frontend from backend (if needed)

If you want to deploy the frontend separately (e.g., on Vercel or Netlify):

1. Move `index.html` to a new repo (or subfolder).
2. Change the `API = ""` line to `API = "https://your-backend.onrender.com"`.
3. Backend already has CORS enabled for all origins, so this works without any backend changes.

## Adding new UI features

Some ideas your teammates can build on top:

- **Quiz mode:** add a section that shows 3 questions and tracks correct/incorrect
- **Notes:** let students save their own notes tied to timestamps
- **Progress sync:** save watch progress to a `progress` table and show it across devices
- **Sidebar nav:** add a lesson list sidebar that shows which lessons are completed

For all of these, the backend pattern is: add a new endpoint in `app.py`, then call it from `index.html`. No build pipeline, no npm install, no bundler.