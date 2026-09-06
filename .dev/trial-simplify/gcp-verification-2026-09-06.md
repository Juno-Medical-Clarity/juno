# Live GCP Verification — 2026-09-06

**Method.** Every command below was run read-only against project `juno-medical-clarity`
(region `us-central1` where applicable), authenticated as `tejitpabari99@gmail.com`
(confirmed via `gcloud auth list` / `gcloud config list` before running anything). No
resource was created, modified, enabled, disabled, or deleted, and `RETENTION_DRY_RUN`
was not touched. This document supersedes `.dev/trial-simplify/README.md`'s
infrastructure-status claims and `gcp-verification-2026-09-05.md` for anything that
conflicts, since it is a fresh, later, read-only check. It does not replace those files;
they are left as historical record per instruction.

---

## 1. Firestore TTL — `care_plan_outputs.expires_at`

Command:
```
gcloud firestore fields ttls list --collection-group=care_plan_outputs --project=juno-medical-clarity
```
Output:
```
name: projects/juno-medical-clarity/databases/(default)/collectionGroups/care_plan_outputs/fields/expires_at
ttlConfig:
  state: ACTIVE
```
**Verdict: EXISTS, state ACTIVE.**

## 2. Firestore TTL — `trial_rate_limits.expires_at`

Command:
```
gcloud firestore fields ttls list --collection-group=trial_rate_limits --project=juno-medical-clarity
```
Output:
```
name: projects/juno-medical-clarity/databases/(default)/collectionGroups/trial_rate_limits/fields/expires_at
ttlConfig:
  state: ACTIVE
```
**Verdict: EXISTS, state ACTIVE.**

## 3. `juno-trial-anon-cleanup` Cloud Run Job

Command: `gcloud run jobs list --region=us-central1`
```
JOB                      REGION       LAST RUN AT              CREATED                  CREATED BY
juno-trial-anon-cleanup  us-central1  2026-09-06 01:31:43 UTC  2026-09-05 15:01:15 UTC  github-actions-deploy@juno-medical-clarity.iam.gserviceaccount.com
```

`gcloud run jobs describe juno-trial-anon-cleanup --region=us-central1` (relevant fields):
```
env:
  GCP_PROJECT_ID=juno-medical-clarity
  FIRESTORE_DATABASE_ID=(default)
  FIREBASE_SERVICE_ACCOUNT_JSON=<secret:firebase-service-account:latest>
  RETENTION_DRY_RUN=false          # <-- live value right now, not "true"
executionCount: 2
latestCreatedExecution: juno-trial-anon-cleanup-p4jg4, completionStatus: EXECUTION_SUCCEEDED
```

`gcloud run jobs executions list --job=juno-trial-anon-cleanup --region=us-central1`:
```
EXECUTION                      RUNNING  COMPLETE  CREATED                  RUN BY
juno-trial-anon-cleanup-p4jg4  0        1 / 1     2026-09-06 01:31:43 UTC  juno-scheduler-invoker@juno-medical-clarity.iam.gserviceaccount.com
juno-trial-anon-cleanup-pxwtn  0        1 / 1     2026-09-06 01:21:34 UTC  Tejitpabari99@gmail.com
```

Log line for `pxwtn` (manual run, 01:22:36Z), via `gcloud logging read`:
```
retention: anon user cleanup complete scanned=6 matched=0 deleted=0 errors=0 pages=1 dry_run=True
```

Log line for `p4jg4` (scheduler-triggered run, 01:34:08Z), via `gcloud logging read`:
```
retention: anon user cleanup complete scanned=6 matched=0 deleted=0 errors=0 pages=1 dry_run=False
```

**Verdict: EXISTS.** Both a dry-run execution (`pxwtn`, `dry_run=True`, run manually) and a
live, non-dry-run execution (`p4jg4`, `dry_run=False`, triggered by
`juno-scheduler-invoker` — i.e. by Cloud Scheduler, not a human) have completed
successfully in production. Both scanned 6 accounts, matched 0, deleted 0 — identical
numbers to what `final-verification-2026-09-05.md` reported for its dry run. **The Job's
current live config has `RETENTION_DRY_RUN=false`**, not `true` as pinned by commit
`8f3e4693` — it was evidently flipped after that commit (consistent with
`.dev/trial-simplify/README.md`'s own Manual Steps item 8, "[DONE, 2026-09-06] Flipped
`RETENTION_DRY_RUN` from `true` to `false`"), and the flip has now been exercised live
via a real scheduler-triggered run that deleted nothing (because nothing matched).

## 4. Cloud Scheduler

Command: `gcloud services list --enabled | grep -i scheduler`
```
cloudscheduler.googleapis.com                Cloud Scheduler API
```
**API state: ENABLED** (as of this check). This differs from
`gcp-verification-2026-09-05.md`'s finding of "disabled" — that check was a snapshot from
the prior day; the API has since been enabled.

Command: `gcloud scheduler jobs list --location=us-central1`
```
ID                             LOCATION     SCHEDULE (TZ)        TARGET_TYPE  STATE
juno-trial-anon-cleanup-daily  us-central1  0 4 * * * (Etc/UTC)  HTTP         ENABLED
```

`gcloud scheduler jobs describe juno-trial-anon-cleanup-daily --location=us-central1` (relevant fields):
```
httpTarget.uri: https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/juno-medical-clarity/jobs/juno-trial-anon-cleanup:run
httpTarget.oauthToken.serviceAccountEmail: juno-scheduler-invoker@juno-medical-clarity.iam.gserviceaccount.com
lastAttemptTime: 2026-09-06T01:31:43.592078Z
schedule: 0 4 * * *
scheduleTime (next): 2026-09-06T04:00:01.633790Z
state: ENABLED
```

The scheduler job's `lastAttemptTime` (01:31:43.592078Z) matches the Cloud Run Job
execution `p4jg4`'s creation time (01:31:43.665503Z) to the millisecond, and that
execution's `RUN BY` field is the scheduler's own invoker service account
(`juno-scheduler-invoker@...`) — this is direct, first-hand evidence of an actual
scheduler-triggered end-to-end invocation, not just a config that claims to be wired up.

**Verdict: EXISTS, ENABLED, and end-to-end exercised** (the daily schedule is
`0 4 * * *` UTC; the very first fire already happened out-of-cycle at 01:31 on
2026-09-06, presumably a manual `gcloud scheduler jobs run` per README's manual-steps
log, followed by the next natural fire scheduled for 04:00 UTC the same day).

## 5. GCS lifecycle rule on `gs://juno-medical-clarity-backend`

`gcloud storage buckets describe gs://juno-medical-clarity-backend --format=json` places
this under the key `lifecycle_config` (not `lifecycle`); confirmed via `gsutil lifecycle
get gs://juno-medical-clarity-backend`:
```
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 1, "matchesPrefix": ["care_plan_trial/"]}}]}
```
**Verdict: EXISTS** — exactly one rule, delete at age 1 day, scoped to the
`care_plan_trial/` prefix. Uncontested by any of the three prior documents.

## 6. Cloud Run `min-instances` / `max-instances` — live, right now

`gcloud run services describe juno-api --region=us-central1` (annotations):
```
autoscaling.knative.dev/minScale: 1
autoscaling.knative.dev/maxScale: 10
```

`gcloud run services describe juno-worker --region=us-central1` (annotations):
```
autoscaling.knative.dev/minScale: (not set, i.e. 0)
autoscaling.knative.dev/maxScale: 5
```

`backend/cloudbuild.yaml` (read directly, not executed):
```
juno-api:    --min-instances=1                                   (line 23)
juno-worker: --min-instances=0  --max-instances=3                (lines 35-36)
```

**Verdict:** `backend/cloudbuild.yaml:23`'s `--min-instances=1` for `juno-api` **is live
in production right now** — `juno-api`'s live `minScale` is `1`, not `0`. This confirms
`docs/trial-architecture.md` §8's own analysis (the primary `deploy.yml` →
`cloudbuild.yaml` path never resets `juno-api` to `min-instances=0`, unlike the
rollback-only path) rather than `.dev/trial-simplify/README.md`'s claim that D7
("min-instances=0, no exceptions") "now holds ... across every deploy path." `juno-worker`
is live at effectively `min-instances=0`, matching its own `cloudbuild.yaml` line and D7.
`max-instances` (`juno-api`=10, `juno-worker`=5) matches both docs' "settled" claim,
live — note `juno-worker`'s live `maxScale=5` differs from the `3` literally written in
`cloudbuild.yaml:36`, which is consistent with `trial-architecture.md` §1's own note that
`deploy.yml`'s later `gcloud run services update` step (driven by `WORKER_MAX_INSTANCES`)
overrides whatever `cloudbuild.yaml`'s initial deploy set — not independently
investigated further here since it wasn't in dispute.

## 7. Firebase Hosting sites

`firebase hosting:sites:list --project juno-medical-clarity`:
```
juno-app-99            https://juno-app-99.web.app
juno-medical-clarity   https://juno-medical-clarity.web.app
```
`firebase hosting:channel:list --project juno-medical-clarity --site juno-medical-clarity`:
```
live   Last Release Time: 2026-09-05 20:59:40   https://juno-medical-clarity.web.app
```
`firebase hosting:channel:list --project juno-medical-clarity --site juno-app-99`:
```
live   Last Release Time: 2026-09-05 02:01:58   https://juno-app-99.web.app
```
**Verdict: EXISTS**, both sites present, both with an active `live` channel release from
2026-09-05, consistent with the hosting-split cutover described in
`docs/trial-architecture.md` §1.

## 8. Cloud Tasks queues

`gcloud tasks queues list --location=us-central1`:
```
QUEUE_NAME            STATE    MAX_NUM_OF_TASKS  MAX_RATE (/sec)  MAX_ATTEMPTS
care-plan-jobs        RUNNING  3                 500.0            100
care-plan-jobs-trial  RUNNING  5                 2.0              100
```
**Verdict: EXISTS**, both queues present and `RUNNING`. Uncontested by any prior document.

---

## Reconciliation — which prior account was right, per item

| # | Item | Verdict (2026-09-06) | Supports |
|---|---|---|---|
| 1 | Firestore TTL, `care_plan_outputs` | EXISTS, ACTIVE | `gcp-verification-2026-09-05.md` (ACTIVE). Contradicts `.dev/trial-simplify/README.md`'s "not yet created." |
| 2 | Firestore TTL, `trial_rate_limits` | EXISTS, ACTIVE | Same as above. |
| 3 | `juno-trial-anon-cleanup` Cloud Run Job | EXISTS, dry-run **and** live-run both executed successfully (scanned=6/matched=0/deleted=0 both times) | `final-verification-2026-09-05.md` + commit `8f3e4693` (job created, dry-run tested with these exact numbers). Contradicts README's "not yet created." Goes further than any prior doc: a live (non-dry-run) execution has since also succeeded, triggered by Cloud Scheduler itself. |
| 4 | Cloud Scheduler API + trigger job | API ENABLED; `juno-trial-anon-cleanup-daily` job EXISTS, ENABLED, and has a real recorded scheduler-triggered invocation | `final-verification-2026-09-05.md` ("ENABLED and end-to-end verified") is now correct. `gcp-verification-2026-09-05.md`'s "disabled" finding was accurate for its own point in time (2026-09-05) but is now stale — state changed between the two checks. |
| 5 | GCS lifecycle rule, `care_plan_trial/`, age 1 day | EXISTS | All three prior accounts agree; confirmed. |
| 6 | `juno-api` live `min-instances` | **1**, not 0 | Confirms `docs/trial-architecture.md` §8's analysis (cloudbuild.yaml's `--min-instances=1` is live, never reset by the primary deploy path). Contradicts README's "min-instances=0 ... now holds with no exceptions." `juno-worker` is live at effectively 0, as all sources agree. |
| 7 | Firebase Hosting sites / deployments | Both sites exist, both have a live release from 2026-09-05 | Consistent with `docs/trial-architecture.md` §1's hosting-split description; uncontested. |
| 8 | Cloud Tasks queues | Both exist, both RUNNING | Uncontested. |

**Nothing in this check could not be verified.** Every one of the 8 items above was
checked directly with a read-only command and produced a definitive result; there is no
"could not verify" item this time (the Firebase CLI was available, contrary to the
task's fallback allowance to skip it).
