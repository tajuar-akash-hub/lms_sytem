from pydantic import BaseModel, Field


class ProcessVideoRequest(BaseModel):
    url_or_id: str = Field(..., description="YouTube URL or 11-char video ID")
    module_id: str | None = Field(
        default=None, description="Optional LMS module to link this video to"
    )


class ProcessVideoResponse(BaseModel):
    video_id: str
    source_id: str
    status: str
    n_chunks: int | None = None
    summary: dict | None = None


class PlaylistPollRequest(BaseModel):
    playlist_id: str = Field(
        ..., description="YouTube playlist ID (the part after list=)"
    )
    dry_run: bool = Field(
        default=False,
        description="If true, just report what would be processed",
    )


class LMSWebhookPayload(BaseModel):
    video_url: str = Field(..., description="URL or ID of the video to process")
    source_type: str = Field(
        default="youtube", description="Source platform (youtube, s3, etc.)"
    )
    title: str | None = None
    metadata: dict | None = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    student_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    cited_timestamp: float | None = None
    cited_text: str | None = None
    message_id: str | None = None


class VideoSummaryRead(BaseModel):
    overview: str
    key_concepts: list[str]
    suggested_questions: list[str]


class VideoRead(BaseModel):
    id: str
    source_id: str
    source_type: str
    title: str | None
    transcript_status: str
    summary: VideoSummaryRead | None = None
