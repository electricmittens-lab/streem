name: Update M3U

on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch: {}
  push:
    paths:
      - ".github/workflows/update-m3u.yml"
      - "exptv_find.py"
      - "generate_m3u.py"

jobs:
  refresh:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    outputs:
      changed: ${{ steps.diff.outputs.changed }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          python -m pip install requests beautifulsoup4

      - name: Generate M3U
        run: |
          python generate_m3u.py

      - name: Detect changes
        id: diff
        run: |
          if git status --porcelain | grep -q "Exp.m3u"; then
            echo "changed=true" >> $GITHUB_OUTPUT
          else
            echo "changed=false" >> $GITHUB_OUTPUT
          fi

      - name: Commit & push if changed
        if: steps.diff.outputs.changed == 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add Exp.m3u
          git commit -m "chore: refresh Exp.m3u ($(date -u +'%Y-%m-%dT%H:%M:%SZ'))"
          git push

  retry_if_no_change:
    needs: refresh
    if: needs.refresh.outputs.changed == 'false'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Wait 2 minutes
        run: sleep 120

      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          python -m pip install requests beautifulsoup4

      - name: Generate M3U (retry)
        run: |
          python generate_m3u.py

      - name: Commit & push if changed (retry)
        run: |
          if git status --porcelain | grep -q "Exp.m3u"; then
            git config user.name "github-actions[bot]"
            git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
            git add Exp.m3u
            git commit -m "chore: refresh Exp.m3u (retry $(date -u +'%Y-%m-%dT%H:%M:%SZ'))"
            git push
          else
            echo "No changes after retry."
