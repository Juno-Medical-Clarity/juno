import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const createTrialJobMock = vi.fn();
vi.mock('../../api/trialApi', () => ({ createTrialJob: (...a: unknown[]) => createTrialJobMock(...a) }));
vi.mock('../../analytics/ga', () => ({ trackEvent: vi.fn() }));

import UploadScreen from '../../components/UploadScreen';

function makeFile(name: string, type = 'text/plain') {
  return new File(['hello'], name, { type });
}

describe('UploadScreen', () => {
  beforeEach(() => createTrialJobMock.mockReset());

  it('disables Simplify while authState is not ready', () => {
    render(<UploadScreen authState="pending" onAuthRetry={vi.fn()} onJobCreated={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Simplify' })).toBeDisabled();
  });

  it('shows a validateFiles error and leaves the button disabled on an invalid selection', async () => {
    // applyAccept: false — user-event's default upload() silently drops any file that
    // doesn't match the <input accept> attribute (emulating native file-picker
    // filtering), which would prevent bad.gif from ever reaching our onChange handler.
    // We're testing our own validateFiles() rejection path here, not the browser's
    // file-picker filtering, so that emulation needs to be bypassed.
    const user = userEvent.setup({ applyAccept: false });
    render(<UploadScreen authState="ready" onAuthRetry={vi.fn()} onJobCreated={vi.fn()} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, makeFile('bad.gif'));
    expect(screen.getByText(/Unsupported file type/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Simplify' })).toBeDisabled();
  });

  it('surfaces the too-many-files error when a combined selection exceeds MAX_FILES, instead of silently dropping the extras', async () => {
    const user = userEvent.setup();
    render(<UploadScreen authState="ready" onAuthRetry={vi.fn()} onJobCreated={vi.fn()} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const files = Array.from({ length: 6 }, (_, i) => makeFile(`f${i}.txt`));
    await user.upload(input, files);

    expect(screen.getByText('You can upload up to 5 files at a time (selected 6).')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Simplify' })).toBeDisabled();
  });

  it('de-duplicates an incoming file that matches one already selected by name, size, and lastModified', async () => {
    const user = userEvent.setup();
    render(<UploadScreen authState="ready" onAuthRetry={vi.fn()} onJobCreated={vi.fn()} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['hello'], 'note.txt', { type: 'text/plain', lastModified: 1700000000000 });
    await user.upload(input, file);
    expect(screen.getByText('1 of 5 files · 5 B of 25 MB')).toBeInTheDocument();

    const duplicate = new File(['hello'], 'note.txt', { type: 'text/plain', lastModified: 1700000000000 });
    await user.upload(input, duplicate);

    expect(screen.getByText('1 of 5 files · 5 B of 25 MB')).toBeInTheDocument();
    expect(screen.getAllByText('note.txt')).toHaveLength(1);
  });

  it('enables Simplify on a valid selection + ready auth, and calls onJobCreated on success', async () => {
    createTrialJobMock.mockResolvedValue({ job_id: 'job-1' });
    const onJobCreated = vi.fn();
    const user = userEvent.setup();
    render(<UploadScreen authState="ready" onAuthRetry={vi.fn()} onJobCreated={onJobCreated} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, makeFile('note.txt'));

    const button = screen.getByRole('button', { name: 'Simplify' });
    expect(button).toBeEnabled();
    await user.click(button);

    expect(createTrialJobMock).toHaveBeenCalledOnce();
    expect(onJobCreated).toHaveBeenCalledWith('job-1');
  });
});
