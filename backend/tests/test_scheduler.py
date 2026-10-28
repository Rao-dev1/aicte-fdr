from apscheduler.triggers.cron import CronTrigger

from app import scheduler as sched_mod
from app.db import SessionLocal
from app.models import Deposit, JobRun
from app.scheduler import JOB_ID, run_daily_check, scheduled_time, start_scheduler
from tests.helpers import hdr


def make_verified_deposit(client, maturity: str) -> None:
    inst = client.post("/api/institutions", json={"name": "Sched College", "code": "SCH1"}, headers=hdr("ADMIN")).json()["id"]
    dep = client.post(
        "/api/deposits",
        json={
            "institution_id": inst,
            "reference_no": "FDR-SCHED",
            "bank_name": "State Bank",
            "amount": "5000.00",
            "issue_date": "2026-06-01",
            "maturity_date": maturity,
        },
        headers=hdr("INSTITUTION_USER", inst=inst),
    ).json()
    client.post(f"/api/deposits/{dep['id']}/verify", json={"observations": "ok"}, headers=hdr("REGULATOR_OFFICER"))


def test_manual_run_is_recorded_and_visible_to_admin(client):
    r = client.post("/api/admin/lifecycle-sweep", headers=hdr("ADMIN"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "OK"
    assert "changed" in body

    jobs = client.get("/api/admin/jobs", headers=hdr("ADMIN")).json()
    assert jobs["runs"][0]["trigger"] == "manual"
    assert jobs["runs"][0]["status"] == "OK"
    assert jobs["schedule"].startswith("08:00")


def test_jobs_endpoint_is_admin_only(client):
    assert client.get("/api/admin/jobs", headers=hdr("REGULATOR_OFFICER")).status_code == 403


def test_scheduled_run_applies_status_changes(client):
    make_verified_deposit(client, maturity="2026-11-20")
    result = run_daily_check(trigger="schedule")
    assert result["status"] == "OK"
    with SessionLocal() as db:
        run = db.get(JobRun, result["run_id"])
        assert run.trigger == "schedule"
        assert run.finished_at is not None


def test_failed_run_is_recorded_and_does_not_raise(client, monkeypatch):
    def boom(db, today):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(sched_mod, "lifecycle_sweep", boom)
    result = run_daily_check(trigger="manual")
    assert result["status"] == "FAILED"
    assert "database unavailable" in result["error"]

    with SessionLocal() as db:
        run = db.get(JobRun, result["run_id"])
        assert run.status == "FAILED"


def test_scheduled_time_reads_config(monkeypatch):
    monkeypatch.setenv("DAILY_CHECK_TIME", "07:30")
    when = scheduled_time()
    assert (when.hour, when.minute) == (7, 30)


def test_scheduler_registers_daily_job_at_configured_time(monkeypatch):
    monkeypatch.setenv("DAILY_CHECK_TIME", "07:30")
    sched = start_scheduler(enabled=True, catch_up=False)
    try:
        job = sched.get_job(JOB_ID)
        assert job is not None
        assert isinstance(job.trigger, CronTrigger)
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields["hour"] == "7"
        assert fields["minute"] == "30"
    finally:
        sched.shutdown(wait=False)


def test_scheduler_can_be_disabled():
    assert start_scheduler(enabled=False) is None


def test_today_is_taken_in_indian_time():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.scheduler import today_ist

    assert today_ist() == datetime.now(ZoneInfo("Asia/Kolkata")).date()
