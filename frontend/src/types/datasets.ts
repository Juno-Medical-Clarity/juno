export interface Dataset {
  group: string;
  inputs: string[];
  files: string[];
}

export interface BatchDatasetSelection {
  group: string;
  inputs: 'all' | string[];
  files: string[];
}
