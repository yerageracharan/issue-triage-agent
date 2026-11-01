# Publish this project to GitHub

The project folder is ready to push to a new repository.

1. On GitHub, create a **blank** repository named `issue-triage-agent` under your account.
2. Choose Public or Private according to your portfolio preference.
3. Do not initialise it with a README, licence, or `.gitignore`; those files are already included here.
4. Open a terminal in the extracted `issue-triage-agent` folder and run the commands below.

## Windows PowerShell, macOS, or Linux

```bash
git init -b main
git add .
git commit -m "Build Issue Triage Agent v0.1.0"
git remote add origin https://github.com/yerageracharan/issue-triage-agent.git
git push -u origin main
```

After the push, the README's clone command and GitHub Actions workflow will be available from the new repository.

## Before making the repository public

- Confirm that `.env` files, access tokens, and private issue exports are not staged.
- Review the sample data; it is synthetic and uses placeholder issue URLs.
- Keep the GitHub integration read-only. The current design does not need write permissions.
- Run `python -m pytest` locally and confirm the Actions workflow passes.
