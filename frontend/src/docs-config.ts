export interface DocEntry {
  slug: string;
  name: string;
  content: string;
}

export interface DocsSection {
  id: string;
  title: string;
  basePath: string;
  entries: DocEntry[];
}

import smogMd from './docs/grading/smog.md?raw';
import fkMd from './docs/grading/flesch-kincaid.md?raw';
import dcMd from './docs/grading/dale-chall.md?raw';
import pematMd from './docs/grading/pemat.md?raw';
import samMd from './docs/grading/sam.md?raw';
import cdcMd from './docs/grading/cdc-cci.md?raw';

export const DOCS_SECTIONS: DocsSection[] = [
  {
    id: 'grading',
    title: 'Grading',
    basePath: '/docs/grading',
    entries: [
      { slug: 'smog',           name: 'SMOG',                         content: smogMd },
      { slug: 'flesch-kincaid', name: 'Flesch-Kincaid',               content: fkMd },
      { slug: 'dale-chall',     name: 'Dale-Chall',                   content: dcMd },
      { slug: 'pemat',          name: 'PEMAT',                        content: pematMd },
      { slug: 'sam',            name: 'SAM',                          content: samMd },
      { slug: 'cdc-cci',        name: 'CDC Clear Communication Index', content: cdcMd },
    ],
  },
  // To add a new section: append one object here. No structural changes needed.
];
