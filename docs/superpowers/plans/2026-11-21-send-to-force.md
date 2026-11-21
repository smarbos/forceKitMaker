# Send to Force — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Export + copy the current program to the Force over SSH, with settings in the page.
**Architecture:** `forcekit/send.py` (ssh + tar stream), config fields, 4 server routes, page button + settings panel.
**Tech Stack:** Python stdlib (`subprocess`, `tarfile`, `shlex`), vanilla JS, pytest, Playwright.
**Spec:** `docs/superpowers/specs/2026-11-21-send-to-force-design.md`

## Global Constraints
- Defaults: host `192.168.0.27`, user `root`, dir `/media/96B6-573E/forcekit`.
- ssh options: `-o BatchMode=yes -o ConnectTimeout=6`; never prompt, never store passwords.
- Remote layout: `<force_dir>/<Drums|Synths>/<Name>/<Name>.xpm` + `<Name>_[ProgramData]/`.

## Review Focus
1. Names with spaces, quotes, `$`, brackets — remote commands must be shell-quoted.
2. Connection lost mid-copy — old kit on the Force untouched, temp folder gone.
3. Force off / wrong IP — error within ~6 s, readable message, page not stuck.
4. Saving settings keeps other keys in config.json (library, port…).
5. Invalid settings (empty host, relative folder, spaces in host) — 400, nothing saved.

### Task 1: config + send module
- Files: `forcekit/config.py`, create `forcekit/send.py`, tests `tests/test_config.py`, `tests/test_send.py`,
  `tests/conftest.py` (fixture `fake_ssh`: executable script that drops `-o X` options and the host, then
  `exec sh -c "$*"`; fixture `force_cfg` = cfg with `force_dir = tmp/force/forcekit`, `ssh_command=[fake]`).
- Produces: `Config.force_host/force_user/force_dir/ssh_command/config_path`; `save_force_settings(cfg, host, user, dir)`;
  `send.ForceError`, `send.SendExists(path)`, `send.test_connection(cfg) -> str`,
  `send.send_program(cfg, folder: Path, overwrite=False) -> str` (remote program folder path).
- Tests: `test_save_force_settings_keeps_other_keys`; `test_send_first_time` (remote has xpm + samples folder);
  `test_send_refuses_existing_without_overwrite` (SendExists); `test_send_overwrite_replaces` (stale sample gone);
  `test_failed_send_keeps_old` (ssh_command that runs the script but tar input is corrupted → old kit intact,
  no `.forcekit-tmp` left); `test_send_quotes_names` (`It's a "$kit" [1]`); `test_connection_ok_and_failure`
  (`ssh_command=["false"]` → ForceError).
- [ ] tests → RED → implement → GREEN → commit.

### Task 2: server routes
- `GET/PUT /api/settings`, `POST /api/settings/test`, `POST /api/send`.
- Tests: settings round trip + 400 on invalid; send 200 then 409 then 200 with overwrite; send with
  failing ssh → 502 with message.
- [ ] tests → RED → implement → GREEN → commit.

### Task 3: page
- Send to Force button (+ inline replace confirm), ⚙ Settings panel (fields, Test, Save).
- Browser check against the scratch server with the fake ssh: send creates the kit under the scratch force dir;
  second send asks to replace; settings save shows the new IP after reload.
- [ ] check → RED → implement → GREEN → commit.

### Task 4: real device
- One real send of a small kit to the Force; list `<force_dir>` over ssh.
