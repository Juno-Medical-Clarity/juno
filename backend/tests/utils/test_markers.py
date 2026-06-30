"""Tests for the Markers registry — lock new Batch marker names."""
from utils.markers.markers import Markers


def test_batch_create_jobs_marker_registered():
    assert Markers.Batch.CreateJobs.name() == "batch.create_jobs"


def test_batch_create_single_job_marker_registered():
    assert Markers.Batch.CreateSingleJob.name() == "batch.create_single_job"
