# Preset Data

Place medical notes here for batch processing. Structure:

```
preset-data/
  GroupName/
    ProcessName/
      file1.pdf
      file2.pdf
```

Each `ProcessName/` folder = one pipeline run. Files inside are merged and processed together.

Supported file types: PDF, TXT, DOCX.

After adding files, run `npm run build` in `frontend/` or push to the `deploy` branch — the preset list updates automatically.
