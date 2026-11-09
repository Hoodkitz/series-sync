"""Tests for domain models."""
from packages.domain.models import SyncJob, VoiceProfile, QAReport, JobStatus
from uuid import uuid4


def test_sync_job():
    sj = SyncJob(tenant_id=uuid4(), source_video_url="https://example.com/video.mp4")
    assert sj.status == JobStatus.UPLOADED
    assert sj.source_language == "en"
    assert sj.target_language == "de"


def test_qa_report():
    qr = QAReport(job_id=uuid4(), lip_sync_score=0.95, audio_quality_score=0.9, translation_accuracy_score=0.88, overall_pass=True)
    assert qr.overall_pass is True
    assert qr.lip_sync_score == 0.95
