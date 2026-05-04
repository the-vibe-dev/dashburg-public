# Windows Runner

This repo includes a bootstrap Windows installer scaffold for the runner.

Current scope:
- create a venv
- install Python dependencies
- copy runner files to a stable home
- seed `config.yaml`
- print the command you should wrap in a Windows service or scheduled task

Install:
```powershell
cd runner\scripts
powershell -ExecutionPolicy Bypass -File .\install_runner_windows.ps1
```

Notes:
- This is not parity-guaranteed with the Linux service path.
- Remote terminal SSH flows still assume a Linux-style target for the terminal host.
- Use Windows runners mainly for job execution, file work, or local service hooks unless you extend the platform support further.
