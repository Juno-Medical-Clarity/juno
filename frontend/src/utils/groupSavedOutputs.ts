export interface SavedOutputMeta {
  id: string; name: string; source_filename: string;
  created_at: string; updated_at: string; batch_group_id: string | null;
}
export interface BatchGroup { batch_group_id: string; items: SavedOutputMeta[] }
export interface DateGroup { date: string; batches: BatchGroup[]; standalone: SavedOutputMeta[] }

export function groupSavedOutputs(outputs: SavedOutputMeta[]): DateGroup[] {
  const dateOrder: string[] = [];
  const byDate = new Map<string, SavedOutputMeta[]>();
  for (const o of outputs) {
    const date = o.created_at.slice(0, 10); // YYYY-MM-DD
    if (!byDate.has(date)) { byDate.set(date, []); dateOrder.push(date); }
    byDate.get(date)!.push(o);
  }
  return dateOrder.map(date => {
    const items = byDate.get(date)!;
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
