# Workbook Automation

Workbook assets and scripts for demo reporting are under `workbooks/end-of-life`.

## Primary scenario

- Software inventory + EOL analysis workbook and report automation

## Fast path

```bash
./workbooks/end-of-life/post-deploy-setup.sh
```

Then run the end-to-end script in that folder:

```bash
cd workbooks/end-of-life
./deploy-eol-solution.sh
```

See `workbooks/end-of-life/README.md` for detailed file-level usage.
