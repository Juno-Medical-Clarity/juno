export interface SavedOutputMeta {
  id: string; name: string; source_filename: string;
  created_at: string; updated_at: string; batch_group_id: string | null;
}
export interface BatchGroup { batch_group_id: string; items: SavedOutputMeta[] }
export interface DateGroup { date: string; batches: BatchGroup[]; standalone: SavedOutputMeta[] }

function padDatePart(value: number): string {
  return String(value).padStart(2, '0');
}

export function localDateKey(date: Date): string {
  return [
    date.getFullYear(),
    padDatePart(date.getMonth() + 1),
    padDatePart(date.getDate()),
  ].join('-');
}

export function formatDateKey(dateKey: string): string {
  const [year, month, day] = dateKey.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

export function groupSavedOutputs(outputs: SavedOutputMeta[]): DateGroup[] {
  const dateOrder: string[] = [];
  const byDate = new Map<string, SavedOutputMeta[]>();
  for (const o of outputs) {
    const date = localDateKey(new Date(o.created_at));
    if (!byDate.has(date)) { byDate.set(date, []); dateOrder.push(date); }
    byDate.get(date)!.push(o);
  }
  // Sort date groups newest-first
  dateOrder.sort((a, b) => b.localeCompare(a));
  return dateOrder.map(date => {
    // Sort items within each date group newest-first by created_at
    const items = byDate.get(date)!.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
    const batchOrder: string[] = [];
    const byBatch = new Map<string, SavedOutputMeta[]>();
    const standalone: SavedOutputMeta[] = [];
    for (const o of items) {
      if (!o.batch_group_id) { standalone.push(o); continue; }
      if (!byBatch.has(o.batch_group_id)) { byBatch.set(o.batch_group_id, []); batchOrder.push(o.batch_group_id); }
      byBatch.get(o.batch_group_id)!.push(o);
    }
    return {
      date,
      batches: batchOrder.map(id => ({ batch_group_id: id, items: byBatch.get(id)! })),
      standalone,
    };
  });
}
