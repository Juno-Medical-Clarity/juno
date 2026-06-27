import { describe, it, expect, vi, beforeEach } from 'vitest';
import { authenticatedFetchJson } from '../apiClient';
import { createCarePlanJob, createBatchJobs } from '../jobs';
import { ApiError } from '../../types/errors';

vi.mock('../apiClient');
vi.mock('../firebase', () => ({ API_URL: 'http://localhost:8082' }));
vi.mock('../../constants', () => ({
  CARE_PLAN_JOBS_PATH: '/care_plan/jobs',
  CARE_PLAN_BATCH_JOBS_PATH: '/care_plan/batch/jobs',
}));

const mockFetch = vi.mocked(authenticatedFetchJson);

describe('createCarePlanJob', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('throws ApiError on 422', async () => {
    const err = new ApiError(
      { code: 'VALIDATION_ERROR', message: 'Invalid form', details: null, timestamp: '', path: null, user_hint: null, retryable: false },
      null
    );
    mockFetch.mockRejectedValue(err);
    await expect(createCarePlanJob(new FormData())).rejects.toBeInstanceOf(ApiError);
  });
});

describe('createBatchJobs', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('throws ApiError on 400', async () => {
    const err = new ApiError(
      { code: 'VALIDATION_ERROR', message: 'Bad request', details: null, timestamp: '', path: null, user_hint: null, retryable: false },
      null
    );
    mockFetch.mockRejectedValue(err);
    await expect(createBatchJobs({ selections: [] })).rejects.toBeInstanceOf(ApiError);
  });
});
