# SP5 Live GCP Verification — 2026-09-05

**Scope:** Read-only verification of `.dev/trial-simplify/05-retention-automation/PRD.md` §8
"CI & IAM setup checklist" against live state in `juno-medical-clarity` (`us-central1`).
No resources were created, modified, or deleted. Authenticated as
`tejitpabari99@gmail.com` (Owner-class `gcloud`/`firebase` login), not the CI service
account — this matches the PRD's own instruction that §8/§2 items be run "with your own
(Owner/Editor) `gcloud`/`firebase` login — not with CI's `GCP_SA_KEY`."

## Status Table

| Item | Expected (PRD §8/§4) | Observed | Verdict |
|---|---|---|---|
| Firestore TTL — `care_plan_outputs.expires_at` | `ttlConfig.state: ACTIVE` (§4.1) | `state: ACTIVE` | ✅ |
| Firestore TTL — `trial_rate_limits.expires_at` | `ttlConfig.state: ACTIVE` (§4.1) | `state: ACTIVE` | ✅ |
| Cloud Run Job `juno-trial-anon-cleanup` exists | Deployed via `gcloud run jobs deploy` (§4.7/§2c) | **Does not exist.** `gcloud run jobs list --project=juno-medical-clarity` (all regions) returns 0 items. | ❌ |
| — image / env vars / SA / timeout | `RETENTION_DRY_RUN=true`, `GCP_PROJECT_ID`, `FIRESTORE_DATABASE_ID=(default)`, `FIREBASE_SERVICE_ACCOUNT_JSON` secret, 1800s timeout, 512Mi/1cpu | N/A — job never created, nothing to inspect | ❌ |
| Cloud Run Job executions (dry-run has run) | At least one execution, reviewed per §8 item 2/4 before ever flipping `RETENTION_DRY_RUN` | `gcloud run jobs executions list --job=juno-trial-anon-cleanup` → 0 items (job doesn't exist) | ❌ |
| Cloud Scheduler API enabled | Enabled (implicitly required by §4.8/§2d) | **Not enabled.** `gcloud scheduler jobs list` fails with `SERVICE_DISABLED` for `cloudscheduler.googleapis.com` | ❌ |
| Cloud Scheduler job `juno-trial-anon-cleanup-trigger` | Schedule `0 9 * * *`, target = Run Jobs `:run` URI, OIDC via `juno-scheduler-invoker` (§4.8/§2d) | Cannot exist — API disabled, and no jobs found once enabled by inspection is impossible without enabling the API (not done, per read-only scope) | ❌ |
| SA `juno-scheduler-invoker` exists | Created per §2d | **Does not exist.** `gcloud iam service-accounts list` shows only `juno-worker-invoker`, default compute SA, `firebase-adminsdk-fbsvc`, `github-actions-deploy` | ❌ |
| `roles/run.invoker` on Job for scheduler SA | Bound per §2d | N/A — neither the Job nor the SA exist | ❌ |
| `roles/firebaseauth.admin` on Firebase service-account identity | Granted to identity backing `firebase-service-account` secret (§8 item 1, §2/3c) | **Already granted.** `firebase-adminsdk-fbsvc@juno-medical-clarity.iam.gserviceaccount.com` holds `roles/firebaseauth.admin` at the project level (matches the `client_email` in `juno-medical-clarity-firebase-adminsdk-fbsvc-91f08cee6f.json`) | ✅ |
| GCS lifecycle rule, `care_plan_trial/` prefix, age 1 | Rule `{"action":{"type":"Delete"},"condition":{"age":1,"matchesPrefix":["care_plan_trial/"]}}` merged into `gs://juno-medical-clarity-backend` (§4.10/§2e) | **No lifecycle configuration at all.** `gcloud storage buckets describe gs://juno-medical-clarity-backend --format="json(lifecycle)"` → `null` | ❌ |
| Cloud Tasks queue `care-plan-jobs` | RUNNING | RUNNING (`max-concurrent=3`, `500/sec`) | ✅ |
| Cloud Tasks queue `care-plan-jobs-trial` | RUNNING (§2a) | RUNNING (`max-concurrent=5`, `2/sec`, matches §2a's create command) | ✅ |
| Firebase Hosting site `juno-medical-clarity` | Exists | Exists — `https://juno-medical-clarity.web.app` | ✅ |
| Firebase Hosting site `juno-app-99` | Created per §2f | Exists — `https://juno-app-99.web.app` | ✅ |
| Anonymous sign-in provider | Enabled (Identity Platform) | **Enabled.** Confirmed via Identity Toolkit Admin API (`signIn.anonymous.enabled: true`) — no owner confirmation needed | ✅ |

**Summary:** Firestore TTL (§4.1), the pre-existing Cloud Tasks queues, both Firebase
Hosting sites, the `firebaseauth.admin` grant, and the anonymous sign-in provider are all
correctly set up. **The entire cleanup automation path is not set up**: the Cloud Run Job
was never deployed, so there is no dry-run execution to review, no Scheduler job can point
at it, and the Scheduler invoker service account and IAM binding don't exist because
nothing has created them yet. The Cloud Scheduler API itself is also not enabled on the
project. The GCS lifecycle backstop (§4.10) has not been applied either. In short: **§2
items (a) queue and (f) hosting are done; items (b) TTL is done; items (c), (d), and (e)
are not done.**

## Fix Commands (verbatim from PRD §8, in dependency order)

### 1. Deploy the Cloud Run Job (§8 checklist item 2c)
```bash
export GCP_PROJECT_ID=juno-medical-clarity
export GCP_REGION=us-central1

gcloud run jobs deploy juno-trial-anon-cleanup \
  --image="us-central1-docker.pkg.dev/$GCP_PROJECT_ID/juno/simplify-backend:latest" \
  --region="$GCP_REGION" --project="$GCP_PROJECT_ID" \
  --command=python --args="-m,scripts.cleanup_anonymous_users" \
  --set-env-vars="GCP_PROJECT_ID=$GCP_PROJECT_ID,FIRESTORE_DATABASE_ID=(default),RETENTION_DRY_RUN=true" \
  --set-secrets="FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest" \
  --task-timeout=1800 --max-retries=0 --memory=512Mi --cpu=1
```
Note: confirm the image `us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend:latest`
actually exists in Artifact Registry before running this — it was not checked as part of
this read-only pass (no `run.admin`-adjacent Artifact Registry check was in scope).

### 2. Enable the Cloud Scheduler API (prerequisite for item 3, not explicitly a separate
PRD command but required — `gcloud scheduler jobs create` will otherwise fail the same way
`gcloud scheduler jobs list` did during this verification)
```bash
gcloud services enable cloudscheduler.googleapis.com --project=juno-medical-clarity
```

### 3. Create the Scheduler invoker SA, grant it `run.invoker`, and create the Scheduler job (§8 checklist item 2d)
```bash
export GCP_PROJECT_ID=juno-medical-clarity
export GCP_REGION=us-central1

gcloud iam service-accounts create juno-scheduler-invoker \
  --project="$GCP_PROJECT_ID" \
  --display-name="Cloud Scheduler -> Cloud Run Jobs invoker"

gcloud run jobs add-iam-policy-binding juno-trial-anon-cleanup \
  --region="$GCP_REGION" --project="$GCP_PROJECT_ID" \
  --member="serviceAccount:juno-scheduler-invoker@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

gcloud scheduler jobs create http juno-trial-anon-cleanup-trigger \
  --location="$GCP_REGION" --project="$GCP_PROJECT_ID" \
  --schedule="0 9 * * *" \
  --uri="https://$GCP_REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$GCP_PROJECT_ID/jobs/juno-trial-anon-cleanup:run" \
  --http-method=POST \
  --oauth-service-account-email="juno-scheduler-invoker@$GCP_PROJECT_ID.iam.gserviceaccount.com"
```

### 4. Add the GCS lifecycle rule on the trial upload prefix (§8 checklist item 2e)
```bash
cat > /tmp/trial-lifecycle-rule.json <<'EOF'
{"rule":[{"action":{"type":"Delete"},"condition":{"age":1,"matchesPrefix":["care_plan_trial/"]}}]}
EOF
gsutil lifecycle get gs://juno-medical-clarity-backend > /tmp/existing-lifecycle.json  # inspect first — was null/empty at verification time, so a plain `set` is safe
gsutil lifecycle set /tmp/trial-lifecycle-rule.json gs://juno-medical-clarity-backend
```
(Verification found the bucket's current lifecycle config is empty/`null`, so no merge
is needed this time — the PRD's "merge, don't overwrite" caveat doesn't currently apply,
but re-check with `lifecycle get` immediately before `set` in case something else was
added since this report.)

### 5. Verify the Cloud Run Job dry-run before ever flipping `RETENTION_DRY_RUN`
After step 1 above (and once at least one scheduled or manually-triggered execution has
run and its logs have been reviewed per §7/§8 item 2), confirm:
```bash
gcloud run jobs executions list --job=juno-trial-anon-cleanup --region=us-central1 --project=juno-medical-clarity
```
**Do not** run `gcloud run jobs update ... --update-env-vars=RETENTION_DRY_RUN=false`
until that review is done — this is a deliberate manual gate per PRD §8 item 2/4, not
something to automate.

## Items confirmed correct, no action needed
- Firestore TTL on `care_plan_outputs.expires_at` and `trial_rate_limits.expires_at`: both `ACTIVE`.
- Cloud Tasks queues `care-plan-jobs` and `care-plan-jobs-trial`: both `RUNNING`.
- Firebase Hosting sites `juno-medical-clarity` and `juno-app-99`: both exist.
- `roles/firebaseauth.admin` already granted to `firebase-adminsdk-fbsvc@juno-medical-clarity.iam.gserviceaccount.com`.
- Anonymous sign-in provider enabled in Identity Platform.

## Method notes
- Authenticated via the existing `gcloud auth list` active account (`tejitpabari99@gmail.com`),
  which already had project access — the bundled service-account keys
  (`gcp-sa-key.json`, `juno-medical-clarity-firebase-adminsdk-*.json`) were not needed for
  this read pass since no permission errors were encountered.
- No IAM-permission-denied failures occurred on any check in this report; all ❌ items are
  genuinely absent resources, not permission blind spots.
- The installed `gcloud` (570.0.0) does not expose `firestore fields ttls describe` — used
  `firestore fields ttls list` instead, which returns the same `ttlConfig.state` field per
  collection group.
