from app.services.scheduler import JOB_ID, SCORES_JOB_ID, run_scores_sync_job, start_scheduler


def _job_ids(scheduler) -> set[str]:
    return {job.id for job in scheduler.get_jobs()}


def test_no_toggle_registers_no_jobs(monkeypatch):
    monkeypatch.delenv("ENABLE_INJURY_SCHEDULER", raising=False)
    monkeypatch.delenv("ENABLE_SCORES_SCHEDULER", raising=False)
    scheduler = start_scheduler()
    try:
        assert _job_ids(scheduler) == set()
    finally:
        scheduler.shutdown()


def test_only_injury_toggle_registers_only_injury_job(monkeypatch):
    monkeypatch.setenv("ENABLE_INJURY_SCHEDULER", "true")
    monkeypatch.delenv("ENABLE_SCORES_SCHEDULER", raising=False)
    scheduler = start_scheduler()
    try:
        assert _job_ids(scheduler) == {JOB_ID}
    finally:
        scheduler.shutdown()


def test_only_scores_toggle_registers_only_scores_job(monkeypatch):
    monkeypatch.delenv("ENABLE_INJURY_SCHEDULER", raising=False)
    monkeypatch.setenv("ENABLE_SCORES_SCHEDULER", "true")
    scheduler = start_scheduler()
    try:
        assert _job_ids(scheduler) == {SCORES_JOB_ID}
    finally:
        scheduler.shutdown()


def test_both_toggles_register_both_jobs(monkeypatch):
    monkeypatch.setenv("ENABLE_INJURY_SCHEDULER", "true")
    monkeypatch.setenv("ENABLE_SCORES_SCHEDULER", "true")
    scheduler = start_scheduler()
    try:
        assert _job_ids(scheduler) == {JOB_ID, SCORES_JOB_ID}
    finally:
        scheduler.shutdown()


def test_run_scores_sync_job_without_api_key_does_not_raise(monkeypatch):
    monkeypatch.delenv("BALLDONTLIE_API_KEY", raising=False)
    run_scores_sync_job()  # ne doit pas lever, seulement journaliser un avertissement
